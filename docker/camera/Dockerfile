# The car's cabin camera, played from dataset clips (Docker Desktop on Windows can't reach a webcam).
# Build context = repo root; what goes in: docker/camera/Dockerfile.dockerignore. Modes: entrypoint.sh.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# Same versions as backend/requirements.txt; imageio-ffmpeg ships its own ffmpeg binary.
RUN pip install imageio-ffmpeg==0.8.1 "websockets>=13"

WORKDIR /app
COPY tools/camera_stream.py tools/
COPY rivian_model/klip_po_voznji.py rivian_model/
COPY docker/camera/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
