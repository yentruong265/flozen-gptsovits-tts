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

RUN python3.10 -m pip install --no-cache-dir \
    torch==2.3.1+cu121 \
    torchaudio==2.3.1+cu121 \
    torchvision==0.18.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

RUN git clone https://github.com/RVC-Boss/GPT-SoVITS.git /app/GPT-SoVITS

RUN mkdir -p /app/GPT-SoVITS/GPT_SoVITS/pretrained_models && \
    git clone https://huggingface.co/lj1995/GPT-SoVITS /tmp/gptsovits_models && \
    cp -r /tmp/gptsovits_models/chinese-hubert-base /app/GPT-SoVITS/GPT_SoVITS/pretrained_models/ && \
    cp -r /tmp/gptsovits_models/chinese-roberta-wwm-ext-large /app/GPT-SoVITS/GPT_SoVITS/pretrained_models/ && \
    cp -r /tmp/gptsovits_models/gsv-v2final-pretrained /app/GPT-SoVITS/GPT_SoVITS/pretrained_models/ && \
    cp -r /tmp/gptsovits_models/fast_langdetect /app/GPT-SoVITS/GPT_SoVITS/pretrained_models/ && \
    rm -rf /tmp/gptsovits_models

WORKDIR /app/GPT-SoVITS

RUN python3.10 -m pip install -r requirements.txt

RUN python3.10 -m pip install --force-reinstall --no-cache-dir \
    torch==2.3.1+cu121 \
    torchaudio==2.3.1+cu121 \
    torchvision==0.18.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python3.10 -m pip install -r /app/requirements.txt

RUN python3.10 -m pip install --force-reinstall --no-cache-dir \
    torch==2.3.1+cu121 \
    torchaudio==2.3.1+cu121 \
    torchvision==0.18.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

COPY handler.py /app/handler.py

EXPOSE 9880

CMD bash -lc "cd /app/GPT-SoVITS && echo 'Starting GPT-SoVITS api_v2...' && python3.10 api_v2.py -a 0.0.0.0 -p 9880 > /tmp/gptsovits_api.log 2>&1 & sleep 180 && echo '===== GPT-SoVITS API LOG =====' && cat /tmp/gptsovits_api.log && echo '===== PORT CHECK =====' && curl -v http://127.0.0.1:9880 || true && cd /app && python3.10 handler.py"