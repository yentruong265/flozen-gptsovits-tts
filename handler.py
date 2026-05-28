import os
import uuid
import subprocess
import requests
import runpod
import boto3

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")
R2_PUBLIC_BASE_URL = os.getenv("R2_PUBLIC_BASE_URL")

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
)

def download_file(url, path):
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)

def convert_to_ref_wav(input_path, output_path):
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "24000",
        "-vn",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg convert failed: {result.stderr}")

def upload_to_r2(local_path, key):
    s3.upload_file(
        local_path,
        R2_BUCKET,
        key,
        ExtraArgs={"ContentType": "audio/wav"}
    )
    return f"{R2_PUBLIC_BASE_URL}/{key}"

def synthesize_gptsovits(text, ref_audio_path, prompt_text, out_path):
    payload = {
        "text": text,
        "text_lang": "vi",
        "ref_audio_path": ref_audio_path,
        "prompt_text": prompt_text,
        "prompt_lang": "vi",
        "top_k": 15,
        "top_p": 1.0,
        "temperature": 1.0,
        "text_split_method": "cut5",
        "batch_size": 1,
        "batch_threshold": 0.75,
        "split_bucket": True,
        "speed_factor": 1.0,
        "fragment_interval": 0.3,
        "seed": -1,
        "media_type": "wav",
        "streaming_mode": False,
        "parallel_infer": True,
        "repetition_penalty": 1.35
    }

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

    text = job.get("text", "").strip()
    ref_audio_url = job.get("ref_audio_url", "").strip()
    prompt_text = job.get("prompt_text", "").strip()

    if not text:
        return {"status": "failed", "error": "Missing text"}

    if not ref_audio_url:
        return {"status": "failed", "error": "Missing ref_audio_url"}

    job_id = job.get("job_id") or str(uuid.uuid4())

    workdir = f"/tmp/{job_id}"
    os.makedirs(workdir, exist_ok=True)

    raw_audio_path = f"{workdir}/raw_voice"
    ref_audio_path = f"{workdir}/ref.wav"
    out_path = f"{workdir}/output.wav"

    download_file(ref_audio_url, raw_audio_path)
    convert_to_ref_wav(raw_audio_path, ref_audio_path)

    if not prompt_text:
        prompt_text = "Xin chào mọi người, hôm nay tôi muốn chia sẻ một câu chuyện ngắn."

    synthesize_gptsovits(
        text=text,
        ref_audio_path=ref_audio_path,
        prompt_text=prompt_text,
        out_path=out_path
    )

    r2_key = f"tts/{job_id}/output.wav"
    audio_url = upload_to_r2(out_path, r2_key)

    return {
        "status": "success",
        "job_id": job_id,
        "audio_url": audio_url
    }

runpod.serverless.start({"handler": handler})