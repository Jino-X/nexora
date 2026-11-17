# Nexora core API (FastAPI). Build from the repo root:
#   docker build -f infrastructure/docker/api.Dockerfile -t nexora-api .
FROM python:3.13.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY services/api/pyproject.toml services/api/README.md ./
COPY services/api/app ./app
RUN pip install --upgrade pip && pip install ".[aws]" \
 && useradd --create-home --uid 10001 nexora && mkdir -p /data && chown nexora /data

USER nexora
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')"
# Workers > 1 need Redis-backed run buffers / rate limits (see docs/deployment.md).
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
