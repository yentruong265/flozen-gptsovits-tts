FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && apt-get install -y \
    git ffmpeg libsndfile1 build-essential \
    python3.10 python3-pip python3.10-venv curl \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/RVC-Boss/GPT-SoVITS.git /app/GPT-SoVITS

WORKDIR /app/GPT-SoVITS

RUN python3.10 -m pip install --upgrade pip
RUN python3.10 -m pip install -r requirements.txt

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python3.10 -m pip install -r /app/requirements.txt

COPY handler.py /app/handler.py

EXPOSE 9880

CMD bash -lc "cd /app/GPT-SoVITS && python3.10 api_v2.py -a 127.0.0.1 -p 9880 & sleep 20 && cd /app && python3.10 handler.py"
