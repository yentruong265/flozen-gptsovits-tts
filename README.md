# FlozenAI GPT-SoVITS RunPod Serverless v15

This package fixes:
- Docker Hub secret names
- startup waiting for api_v2 readiness
- unsupported `vi` language code
- bad `all_zh` default that caused fast_langdetect issues
- reference audio duration validation
- output audio duration/size validation

## Deploy

Replace your repo files with these files, then:

```bash
git add .
git commit -m "GPT-SoVITS stable v15"
git push
```

After GitHub Actions succeeds, create a new RunPod release with:

```text
yentruongngoc/flozen-gptsovits-tts:v15
```

Required RunPod environment variables:

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET
R2_PUBLIC_BASE_URL
```

## Recommended Vietnamese test payload

GPT-SoVITS v2 does not officially support `vi`. Default mode is `en` because Vietnamese uses Latin script and avoids fast_langdetect/all_zh issues.

```json
{
  "input": {
    "job_id": "test_clone_vi_015",
    "text": "lý thuyết trò chơi là một thứ cực kỳ uyên bác bắt nguồn từ toán học.",
    "ref_audio_url": "https://pub-93764efb31b244babb2bc41d8cb399bb.r2.dev/voice/Yen_voice296.m4a",
    "prompt_text": "Transcript đúng của đoạn 8 giây đầu trong audio mẫu.",
    "text_lang": "en",
    "prompt_lang": "en",
    "ref_start_sec": 0,
    "ref_duration_sec": 8,
    "speed_factor": 1.0
  }
}
```

If `en` sounds poor, you may test:

```json
"text_lang": "all_zh",
"prompt_lang": "all_zh"
```

but `all_zh` may trigger fast language detection and can be unstable for Vietnamese.
