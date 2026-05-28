import os
import uuid
import json
import subprocess
import wave
from pathlib import Path

import boto3
import requests
import runpod


SERVICE_VERSION = "flozen-gptsovits-runpod-v12"


R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")
R2_PUBLIC_BASE_URL = (os.getenv("R2_PUBLIC_BASE_URL") or "").rstrip("/")

GPT_SOVITS_URL = os.getenv("GPT_SOVITS_URL", "http://127.0.0.1:9880/tts")


def get_s3_client():
    missing = [
        name
        for name, value in {
            "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
            "R2_ACCESS_KEY_ID": R2_ACCESS_KEY_ID,
            "R2_SECRET_ACCESS_KEY": R2_SECRET_ACCESS_KEY,
            "R2_BUCKET": R2_BUCKET,
            "R2_PUBLIC_BASE_URL": R2_PUBLIC_BASE_URL,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing R2 environment variables: {', '.join(missing)}")

    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    )


def download_file(url: str, path: str) -> None:
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("ref_audio_url must be a public http/https URL")

    with requests.get(url, timeout=180, stream=True) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def run_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(cmd)
            + "\nSTDOUT:\n"
            + result.stdout[-4000:]
            + "\nSTDERR:\n"
            + result.stderr[-4000:]
        )
    return result


def convert_to_ref_wav(input_path: str, output_path: str, start_sec: float = 0.0, duration_sec: float = 8.0) -> None:
    """
    GPT-SoVITS v2 requires reference audio in the 3-10s range.
    We force a stable 24kHz mono wav and trim to duration_sec.
    """
    duration_sec = max(3.0, min(float(duration_sec), 10.0))
    start_sec = max(0.0, float(start_sec))

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_sec),
        "-i",
        input_path,
        "-t",
        str(duration_sec),
        "-ac",
        "1",
        "-ar",
        "24000",
        "-vn",
        "-af",
        "silenceremove=start_periods=1:start_duration=0.15:start_threshold=-45dB,"
        "loudnorm=I=-18:TP=-2:LRA=11",
        output_path,
    ]
    run_cmd(cmd)

    actual_duration = wav_duration(output_path)
    if actual_duration < 3.0 or actual_duration > 10.5:
        raise RuntimeError(
            f"Reference audio after conversion must be 3-10s, got {actual_duration:.2f}s. "
            "Use ref_start_sec/ref_duration_sec or upload a 3-10s clean sample."
        )


def wav_duration(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def upload_to_r2(local_path: str, key: str) -> str:
    s3 = get_s3_client()
    s3.upload_file(
        local_path,
        R2_BUCKET,
        key,
        ExtraArgs={"ContentType": "audio/wav"},
    )
    return f"{R2_PUBLIC_BASE_URL}/{key}"


def normalize_gptsovits_lang(value: str, default: str = "all_zh") -> str:
    """
    GPT-SoVITS v2 official language dictionary does not include Vietnamese.
    For Vietnamese we use all_zh as the practical multilingual frontend mode.
    """
    v = (value or default).strip().lower()
    aliases = {
        "vi": "all_zh",
        "vn": "all_zh",
        "vie": "all_zh",
        "vietnamese": "all_zh",
        "zh-cn": "zh",
        "cn": "zh",
        "chinese": "zh",
        "english": "en",
        "jp": "ja",
        "japanese": "ja",
        "kr": "ko",
        "korean": "ko",
        "cantonese": "yue",
    }
    v = aliases.get(v, v)

    supported = {
        "zh",
        "en",
        "ja",
        "ko",
        "yue",
        "all_zh",
        "all_en",
        "all_ja",
        "all_ko",
        "all_yue",
    }
    return v if v in supported else default


def synthesize_gptsovits(
    text: str,
    ref_audio_path: str,
    prompt_text: str,
    out_path: str,
    text_lang: str = "all_zh",
    prompt_lang: str = "all_zh",
    speed_factor: float = 1.0,
) -> None:
    payload = {
        "text": text,
        "text_lang": normalize_gptsovits_lang(text_lang),
        "ref_audio_path": ref_audio_path,
        "prompt_text": prompt_text,
        "prompt_lang": normalize_gptsovits_lang(prompt_lang),
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
        "repetition_penalty": 1.35,
    }

    resp = requests.post(GPT_SOVITS_URL, json=payload, timeout=900)

    if resp.status_code >= 400:
        raise RuntimeError(
            "GPT-SoVITS /tts failed: "
            f"status={resp.status_code}, body={resp.text}, payload={json.dumps(payload, ensure_ascii=False)}"
        )

    content_type = (resp.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        raise RuntimeError(f"Expected wav bytes but got JSON: {resp.text}")

    if not resp.content or len(resp.content) < 1024:
        raise RuntimeError(f"GPT-SoVITS returned empty/small audio: {len(resp.content)} bytes")

    with open(out_path, "wb") as f:
        f.write(resp.content)


def handler(event):
    print(f"### {SERVICE_VERSION} ###", flush=True)

    job = event.get("input", {}) or {}

    text = (job.get("text") or "").strip()
    ref_audio_url = (job.get("ref_audio_url") or "").strip()
    prompt_text = (job.get("prompt_text") or "").strip()

    if not text:
        return {"status": "failed", "error": "Missing text", "service_version": SERVICE_VERSION}

    if not ref_audio_url:
        return {"status": "failed", "error": "Missing ref_audio_url", "service_version": SERVICE_VERSION}

    if not prompt_text:
        return {
            "status": "failed",
            "error": (
                "Missing prompt_text. For GPT-SoVITS, prompt_text should be the transcript "
                "of the 3-10 second reference audio sample."
            ),
            "service_version": SERVICE_VERSION,
        }

    job_id = job.get("job_id") or str(uuid.uuid4())
    safe_job_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(job_id))

    ref_start_sec = float(job.get("ref_start_sec", 0))
    ref_duration_sec = float(job.get("ref_duration_sec", 8))
    text_lang = job.get("text_lang", "all_zh")
    prompt_lang = job.get("prompt_lang", "all_zh")
    speed_factor = float(job.get("speed_factor", 1.0))

    workdir = Path(f"/tmp/{safe_job_id}")
    workdir.mkdir(parents=True, exist_ok=True)

    raw_audio_path = str(workdir / "raw_voice")
    ref_audio_path = str(workdir / "ref.wav")
    out_path = str(workdir / "output.wav")

    download_file(ref_audio_url, raw_audio_path)
    convert_to_ref_wav(raw_audio_path, ref_audio_path, ref_start_sec, ref_duration_sec)

    synthesize_gptsovits(
        text=text,
        ref_audio_path=ref_audio_path,
        prompt_text=prompt_text,
        out_path=out_path,
        text_lang=text_lang,
        prompt_lang=prompt_lang,
        speed_factor=speed_factor,
    )

    r2_key = f"tts/{safe_job_id}/output.wav"
    audio_url = upload_to_r2(out_path, r2_key)

    return {
        "status": "success",
        "job_id": safe_job_id,
        "audio_url": audio_url,
        "service_version": SERVICE_VERSION,
    }


runpod.serverless.start({"handler": handler})
