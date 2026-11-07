# Backend image: the same code runs as the coordinator (in the car) or the server (accounts, history, report).
# The role is the uvicorn app picked by the compose file (docker/car.yml, docker/server.yml):
#   coordinator: uvicorn app.coordinator.main:app --port 8000
#   server:      uvicorn app.server.main:app --port 8001
# Build context is the repo root (the coordinator reads notebooks/risk_config.json); what goes in is listed in
# backend/Dockerfile.dockerignore.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RISK_CONFIG_PATH=/app/risk_config.json \
    VIDEO_CACHE_DIR=/tmp/video-cache

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY notebooks/risk_config.json ./risk_config.json
COPY backend/app ./app

# Both roles answer GET /api/v1/health; the compose file passes the port.
ENV PORT=8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=12 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/v1/health', timeout=2)"

CMD ["sh", "-c", "exec uvicorn ${APP:-app.coordinator.main:app} --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
