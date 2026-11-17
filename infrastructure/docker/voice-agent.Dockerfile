# Nexora voice agent (LiveKit Agents). Build from the repo root:
#   docker build -f infrastructure/docker/voice-agent.Dockerfile -t nexora-voice-agent .
FROM python:3.13.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY services/voice-agent/pyproject.toml ./
COPY services/voice-agent/src ./src
RUN pip install --upgrade pip && pip install . \
 && useradd --create-home --uid 10001 nexora
USER nexora
# Bake VAD + turn-detector weights into the image so cold starts don't download them.
RUN python -m nexora_voice.main download-files
CMD ["python", "-m", "nexora_voice.main", "start"]
