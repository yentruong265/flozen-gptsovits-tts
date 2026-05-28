# FlozenAI GPT-SoVITS RunPod Serverless fixed package

Files included:
- Dockerfile
- handler.py
- requirements.txt
- .github/workflows/docker-build.yml

Deploy:
1. Replace your current files with these files.
2. git add .
3. git commit -m "Fix GPT-SoVITS RunPod serverless v12"
4. git push
5. Wait for GitHub Actions to complete.
6. RunPod > Manage > New Release > image:
   yentruongngoc/flozen-gptsovits-tts:v12

Test input example:
{
  "input": {
    "job_id": "test_clone_vi_012",
    "text": "Xin chào, đây là bản thử nghiệm clone giọng tiếng Việt cho FlozenAI.",
    "ref_audio_url": "https://pub-93764efb31b244babb2bc41d8cb399bb.r2.dev/voice/Yen_voice_short.wav",
    "prompt_text": "Transcript chính xác của file audio mẫu 3 đến 10 giây.",
    "text_lang": "all_zh",
    "prompt_lang": "all_zh",
    "ref_start_sec": 0,
    "ref_duration_sec": 8,
    "speed_factor": 1.0
  }
}
