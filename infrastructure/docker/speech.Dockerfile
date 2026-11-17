# Nexora speech server (IndicConformer STT + Indic Parler-TTS). CPU image by default.
# For NVIDIA GPUs, swap the base for an official PyTorch CUDA runtime image and install the CUDA
# wheels of torch/torchaudio.
#   docker build -f infrastructure/docker/speech.Dockerfile -t nexora-speech .
FROM python:3.13.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg && rm -rf /var/lib/apt/lists/*
COPY services/speech/pyproject.toml ./
COPY services/speech/speech_server ./speech_server
RUN pip install --upgrade pip && pip install ".[models]" \
 && useradd --create-home --uid 10001 nexora && mkdir -p /models && chown nexora /models
USER nexora
EXPOSE 8100
# Models download into the /models volume on first start (several GB); warm-up runs after loading.
CMD ["uvicorn", "speech_server.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100"]
