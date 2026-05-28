FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV HF_HUB_ENABLE_HF_TRANSFER=0

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git git-lfs ffmpeg libsndfile1 build-essential \
    python3.10 python3-pip python3.10-venv curl ca-certificates \
    && git lfs install \
    && rm -rf /var/lib/apt/lists/*

RUN python3.10 -m pip install --upgrade pip setuptools wheel

# Pin PyTorch CUDA 12.1 for RunPod driver compatibility.
RUN python3.10 -m pip install --no-cache-dir \
    torch==2.3.1+cu121 \
    torchaudio==2.3.1+cu121 \
    torchvision==0.18.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# Clone GPT-SoVITS.
RUN git clone https://github.com/RVC-Boss/GPT-SoVITS.git /app/GPT-SoVITS

# Download pretrained models through huggingface_hub, not git-lfs clone.
RUN python3.10 -m pip install --no-cache-dir huggingface_hub

RUN mkdir -p /app/GPT-SoVITS/GPT_SoVITS/pretrained_models && \
    python3.10 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='lj1995/GPT-SoVITS', local_dir='/app/GPT-SoVITS/GPT_SoVITS/pretrained_models', local_dir_use_symlinks=False, resume_download=True)"

WORKDIR /app/GPT-SoVITS

RUN python3.10 -m pip install -r requirements.txt

# Re-pin torch because GPT-SoVITS requirements may overwrite it.
RUN python3.10 -m pip install --force-reinstall --no-cache-dir \
    torch==2.3.1+cu121 \
    torchaudio==2.3.1+cu121 \
    torchvision==0.18.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python3.10 -m pip install -r /app/requirements.txt

# Final torch pin after custom requirements.
RUN python3.10 -m pip install --force-reinstall --no-cache-dir \
    torch==2.3.1+cu121 \
    torchaudio==2.3.1+cu121 \
    torchvision==0.18.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

COPY handler.py /app/handler.py
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 9880

CMD ["/app/start.sh"]
