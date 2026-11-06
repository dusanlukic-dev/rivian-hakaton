# Model worker container (planned, not built or tested yet). Build from the repo root:
#   docker build -f model/Dockerfile -t safety-model .
#   docker run --rm -e COORDINATOR_URL=ws://host.docker.internal:8000/api/v1/model/ws safety-model
# notebooks/models/ must exist first (notebooks/setup_models.*). The CV code is copied as it is.
FROM python:3.12-slim

# mediapipe pulls in opencv-contrib-python, which needs these shared libraries
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY model/requirements.txt model/requirements.txt
RUN pip install --no-cache-dir -r model/requirements.txt

COPY notebooks/risk_pipeline.py notebooks/risk_config.json notebooks/
COPY notebooks/models notebooks/models
COPY model/worker.py model/worker.py

ENV COORDINATOR_URL=ws://coordinator:8000/api/v1/model/ws PYTHONUNBUFFERED=1
CMD ["python", "model/worker.py"]
