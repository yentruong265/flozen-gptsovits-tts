import os
import uuid
import subprocess
import requests
import runpod
import boto3

VERSION = "v15-fixed-en-default"
print(f"### FLOZEN GPT-SOVITS HANDLER VERSION: {VERSION} ###", flush=True)

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")
R2_PUBLIC_BASE_URL = os.getenv("R2_PUBLIC_BASE_URL")

# GPT-SoVITS v2 does not officially support "vi".
# Default to "en" for Vietnamese Latin-script text to avoid all_zh/fast_langdetect issues.
DEFAULT_TEXT_LANG = os.getenv("GPTSOVITS_DEFAULT_TEXT_LANG", "en").strip().lower()
DEFAULT_PROMPT_LANG = os.getenv("GPTSOVITS_DEFAULT_PROMPT_LANG", "en").strip().lower()

SUPPORTED_LANGS = {"zh", "ja", "en", "ko", "yue", "all_zh", "all_ja", "all_yue", "all_ko"}

if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_PUBLIC_BASE_URL]):
    print("WARNING: One or more R2 environment variables are missing.", flush=True)

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
)

def sanitize_lang(value, default_value):
    lang = str(value or default_value).strip().lower()

    # Do not allow vi/auto because official api_v2 rejects unsupported languages.
    if lang in {"vi", "vn", "auto", "vie"}:
        lang = default_value

    if lang not in SUPPORTED_LANGS:
        lang = default_value

    return lang

def run_cmd(cmd, error_prefix):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{error_prefix}: {result.stderr}")
    return result.stdout.strip()

def download_file(url, path):
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)

def convert_to_ref_wav(input_path, output_path, start_sec=0.0, duration_sec=8.0):
    # GPT-SoVITS v2 requires reference audio around 3-10 seconds.
    duration_sec = max(3.0, min(float(duration_sec), 9.5))
    start_sec = max(0.0, float(start_sec))

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start_sec),
        "-i", input_path,
        "-t", str(duration_sec),
        "-ac", "1",
        "-ar", "24000",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-vn",
        output_path
    ]
    run_cmd(cmd, "ffmpeg convert reference audio failed")

def get_audio_duration(path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return 0.0
    try:
        return float(result.stdout.strip())
    except Exception:
        return 0.0

def get_file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0

def upload_to_r2(local_path, key):
    s3.upload_file(
        local_path,
        R2_BUCKET,
        key,
        ExtraArgs={"ContentType": "audio/wav"}
    )
    return f"{R2_PUBLIC_BASE_URL.rstrip('/')}/{key}"

def synthesize_gptsovits(
    text,
    ref_audio_path,
    prompt_text,
    out_path,
    text_lang,
    prompt_lang,
    speed_factor=1.0
):
    payload = {
        "text": text,
        "text_lang": text_lang,
        "ref_audio_path": ref_audio_path,
        "prompt_text": prompt_text,
        "prompt_lang": prompt_lang,
        "top_k": 15,
        "top_p": 1.0,
        "temperature": 1.0,
        "text_split_method": "cut5",
        "batch_size": 1,
        "batch_threshold": 0.75,
        "split_bucket": True,
        "speed_factor": float(speed_factor),
        "fragment_interval": 0.3,
        "seed": -1,
        "media_type": "wav",
        "streaming_mode": False,
        "parallel_infer": True,
        "repetition_penalty": 1.35
    }

    print(
        f"Calling GPT-SoVITS /tts with text_lang={text_lang}, prompt_lang={prompt_lang}, "
        f"text_len={len(text)}, prompt_len={len(prompt_text)}",
        flush=True
    )

    resp = requests.post(
        "http://127.0.0.1:9880/tts",
        json=payload,
        timeout=600
    )

    if resp.status_code >= 400:
        raise RuntimeError(
            f"GPT-SoVITS /tts failed: status={resp.status_code}, body={resp.text}"
        )

    with open(out_path, "wb") as f:
        f.write(resp.content)

def handler(event):
    job = event.get("input", {})

    text = str(job.get("text", "")).strip()
    ref_audio_url = str(job.get("ref_audio_url", "")).strip()
    prompt_text = str(job.get("prompt_text", "")).strip()
    job_id = str(job.get("job_id") or uuid.uuid4()).strip()

    text_lang = sanitize_lang(job.get("text_lang"), DEFAULT_TEXT_LANG)
    prompt_lang = sanitize_lang(job.get("prompt_lang"), DEFAULT_PROMPT_LANG)

    ref_start_sec = float(job.get("ref_start_sec", 0) or 0)
    ref_duration_sec = float(job.get("ref_duration_sec", 8) or 8)
    speed_factor = float(job.get("speed_factor", 1.0) or 1.0)

    print(f"Received job_id={job_id} | version={VERSION}", flush=True)

    if not text:
        return {"status": "failed", "error": "Missing text"}

    if not ref_audio_url:
        return {"status": "failed", "error": "Missing ref_audio_url"}

    if not prompt_text:
        return {
            "status": "failed",
            "error": "Missing prompt_text transcript. prompt_text must match the selected reference audio segment."
        }

    workdir = f"/tmp/{job_id}"
    os.makedirs(workdir, exist_ok=True)

    raw_audio_path = f"{workdir}/raw_audio"
    ref_audio_path = f"{workdir}/ref.wav"
    out_path = f"{workdir}/output.wav"

    download_file(ref_audio_url, raw_audio_path)

    convert_to_ref_wav(
        raw_audio_path,
        ref_audio_path,
        start_sec=ref_start_sec,
        duration_sec=ref_duration_sec
    )

    ref_duration = get_audio_duration(ref_audio_path)
    if ref_duration < 3.0 or ref_duration > 10.2:
        raise RuntimeError(
            f"Invalid converted reference audio duration: {ref_duration:.2f}s. "
            "Reference audio must be 3-10 seconds."
        )

    synthesize_gptsovits(
        text=text,
        ref_audio_path=ref_audio_path,
        prompt_text=prompt_text,
        out_path=out_path,
        text_lang=text_lang,
        prompt_lang=prompt_lang,
        speed_factor=speed_factor
    )

    output_duration = get_audio_duration(out_path)
    output_size = get_file_size(out_path)

    if output_duration < 2.0 or output_size < 4096:
        raise RuntimeError(
            f"Generated audio invalid: duration={output_duration:.2f}s, size={output_size} bytes. "
            "Check prompt_text, reference audio quality, and language mode. "
            "For Vietnamese with base GPT-SoVITS v2, try text_lang='en' first; if poor, try text_lang='all_zh'."
        )

    r2_key = f"tts/{job_id}/output.wav"
    audio_url = upload_to_r2(out_path, r2_key)

    return {
        "status": "success",
        "job_id": job_id,
        "audio_url": audio_url,
        "output_duration_sec": output_duration,
        "output_size_bytes": output_size,
        "ref_duration_sec": ref_duration,
        "text_lang": text_lang,
        "prompt_lang": prompt_lang,
        "version": VERSION
    }

runpod.serverless.start({"handler": handler})
