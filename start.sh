#!/usr/bin/env bash
set -euo pipefail

echo "### FLOZEN GPT-SOVITS STARTUP VERSION: v15-fixed ###"

echo "Checking pretrained model directory..."
ls -la /app/GPT-SoVITS/GPT_SoVITS/pretrained_models || true
ls -la /app/GPT-SoVITS/GPT_SoVITS/pretrained_models/gsv-v2final-pretrained || true

cd /app/GPT-SoVITS

echo "Starting GPT-SoVITS api_v2 on port 9880..."
python3.10 api_v2.py -a 0.0.0.0 -p 9880 > /tmp/gptsovits_api.log 2>&1 &
API_PID=$!

echo "Waiting for GPT-SoVITS API to become ready..."
READY=0
for i in $(seq 1 240); do
    if ! kill -0 "${API_PID}" 2>/dev/null; then
        echo "GPT-SoVITS api_v2 crashed during startup."
        echo "===== GPT-SoVITS API LOG ====="
        cat /tmp/gptsovits_api.log || true
        exit 1
    fi

    if curl -fsS http://127.0.0.1:9880/ >/dev/null 2>&1; then
        READY=1
        echo "GPT-SoVITS API is ready."
        break
    fi

    sleep 1
done

echo "===== GPT-SoVITS API LOG SNAPSHOT ====="
cat /tmp/gptsovits_api.log || true

if [ "${READY}" != "1" ]; then
    echo "GPT-SoVITS API did not become ready within timeout."
    exit 1
fi

cd /app
echo "Starting RunPod serverless handler..."
python3.10 handler.py
