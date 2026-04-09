# services/whisperlive-wrapper/Dockerfile
# GPU image để Qwen3-ASR chạy được trên CUDA
# (Faster Whisper cũng chạy được trên image này)
FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001
CMD ["python", "main.py"]
