# FlozenAI GPT-SoVITS TTS Service

## Build Docker

```bash
docker build -t flozen-gptsovits-tts .
```

## Push Docker

```bash
docker tag flozen-gptsovits-tts yourdockerhub/flozen-gptsovits-tts:latest
docker push yourdockerhub/flozen-gptsovits-tts:latest
```

## Run Local

```bash
docker run --gpus all -p 9880:9880 flozen-gptsovits-tts
```

## RunPod Env Variables

R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=
R2_PUBLIC_BASE_URL=

## Test Payload

```json
{
  "input": {
    "job_id": "test_clone_vi_001",
    "text": "Xin chào, đây là bản thử nghiệm clone giọng tiếng Việt cho FlozenAI.",
    "ref_audio_url": "https://your-r2-url/sample.wav",
    "prompt_text": "Xin chào mọi người, hôm nay tôi muốn chia sẻ một câu chuyện ngắn."
  }
}
```
