FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV HF_HUB_ENABLE_HF_TRANSFER=0
ENV FTLANG_CACHE=/app/GPT-SoVITS/GPT_SoVITS/pretrained_models/fast_langdetect
ENV is_half=true

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git git-lfs ffmpeg sox libsox-dev libsndfile1 build-essential \
    python3.10 python3-pip python3.10-venv curl ca-certificates \
    && git lfs install \
    && rm -rf /var/lib/apt/lists/*

RUN python3.10 -m pip install --upgrade pip setuptools wheel

# RunPod worker driver seen in logs is CUDA driver 12.1-compatible.
# Do not allow GPT-SoVITS requirements to leave a newer CUDA torch behind.
RUN python3.10 -m pip install --no-cache-dir \
    torch==2.3.1+cu121 \
    torchaudio==2.3.1+cu121 \
    torchvision==0.18.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

RUN git clone --depth=1 https://github.com/RVC-Boss/GPT-SoVITS.git /app/GPT-SoVITS

RUN python3.10 -m pip install --no-cache-dir "huggingface_hub>=0.23.0"

# Official README: pretrained models must be placed under GPT_SoVITS/pretrained_models.
# Use snapshot_download instead of git clone + LFS because GitHub Actions often fails on large LFS clones.
RUN mkdir -p /app/GPT-SoVITS/GPT_SoVITS/pretrained_models && \
    python3.10 - <<'PY'
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="lj1995/GPT-SoVITS",
    local_dir="/app/GPT-SoVITS/GPT_SoVITS/pretrained_models",
    local_dir_use_symlinks=False,
    resume_download=True,
)
PY

WORKDIR /app/GPT-SoVITS

RUN python3.10 -m pip install -r requirements.txt

# Re-pin torch after GPT-SoVITS requirements because they may overwrite torch.
RUN python3.10 -m pip install --force-reinstall --no-cache-dir \
    torch==2.3.1+cu121 \
    torchaudio==2.3.1+cu121 \
    torchvision==0.18.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# Prepare fast-langdetect cache directory. GPT-SoVITS points fast-langdetect to this exact path.
# The directory must exist or fast-langdetect raises FileNotFoundError.
RUN mkdir -p /app/GPT-SoVITS/GPT_SoVITS/pretrained_models/fast_langdetect && \
    python3.10 - <<'PY'
import os
cache_dir = "/app/GPT-SoVITS/GPT_SoVITS/pretrained_models/fast_langdetect"
os.environ["FTLANG_CACHE"] = cache_dir
os.makedirs(cache_dir, exist_ok=True)

try:
    from fast_langdetect import detect
    # Warm up if possible. If this fails because the package API changed, the
    # existing cache directory still prevents the known FileNotFoundError.
    try:
        print("fast_langdetect warmup:", detect("Xin chao moi nguoi"))
    except TypeError:
        print("fast_langdetect warmup:", detect("Xin chao moi nguoi", low_memory=True))
except Exception as e:
    print("fast_langdetect warmup warning:", repr(e))

print("fast_langdetect cache dir ready:", cache_dir)
PY

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python3.10 -m pip install -r /app/requirements.txt

# Final torch pin after service requirements.
RUN python3.10 -m pip install --force-reinstall --no-cache-dir \
    torch==2.3.1+cu121 \
    torchaudio==2.3.1+cu121 \
    torchvision==0.18.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

COPY handler.py /app/handler.py

EXPOSE 9880

CMD bash -lc '\
set -e; \
mkdir -p /app/GPT-SoVITS/GPT_SoVITS/pretrained_models/fast_langdetect; \
cd /app/GPT-SoVITS; \
echo "===== CUDA CHECK ====="; \
python3.10 - <<PY || true
import torch
print("torch:", torch.__version__)
print("cuda_available:", torch.cuda.is_available())
print("cuda:", torch.version.cuda)
print("device:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU")
PY
echo "===== START GPT-SOVITS API ====="; \
python3.10 api_v2.py -a 0.0.0.0 -p 9880 > /tmp/gptsovits_api.log 2>&1 & \
API_PID=$!; \
echo "api pid=${API_PID}"; \
for i in $(seq 1 360); do \
  if ! kill -0 ${API_PID} 2>/dev/null; then \
    echo "GPT-SoVITS API exited before readiness"; \
    cat /tmp/gptsovits_api.log || true; \
    exit 1; \
  fi; \
  python3.10 - <<PY && break || true
import socket
s = socket.socket()
s.settimeout(1)
s.connect(("127.0.0.1", 9880))
s.close()
PY
  if [ "$i" = "360" ]; then \
    echo "GPT-SoVITS API did not open port 9880 in time"; \
    cat /tmp/gptsovits_api.log || true; \
    exit 1; \
  fi; \
  sleep 1; \
done; \
echo "===== GPT-SOVITS API READY ====="; \
tail -n 80 /tmp/gptsovits_api.log || true; \
cd /app; \
exec python3.10 handler.py \
'
