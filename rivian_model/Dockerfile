# Model kontejner (pažnja vozača): radi bez prozora, samo CPU.
# Podrazumevano pokreće rivian_detector.py: model koji se sam javlja koordinatoru
# (protokol iz rivian-hakaton/model/worker.py) i za svaki frejm vraća dokaz po kategoriji.
#
# Izgradnja (težine pravi sam, vidi setup_models.py ispod; ceo auto: ../start.ps1 i docker/car.yml):
#   docker build -t rivian-model .
# Model za koordinator (koordinator na laptopu, port 8000):
#   docker run --rm -e COORDINATOR_URL=ws://host.docker.internal:8000/api/v1/model/ws rivian-model
#   docker run --rm rivian-model rivian_detector.py --camera 05_23 --coordinator ws://host.docker.internal:8000/api/v1/model/ws
# Merenje na jednom klipu iz dataseta (dataset samo za čitanje, izlaz u out_docker/):
#   docker run --rm -v "C:\Users\PC\Downloads\Hackathon dataset 2026\Hackathon dataset 2026:/data:ro"
#              -v "C:\Users\PC\DataspellProjects\rivian_vezba\out_docker:/out"
#              rivian-model pipeline.py /data/08_14_62_092916_video_inCabin.mp4 --no-video --out /out
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    COORDINATOR_URL=ws://host.docker.internal:8000/api/v1/model/ws

# OpenCV i MediaPipe traže libGL i glib čak i bez prozora
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# PyTorch samo za CPU (traži ga Ultralytics); bez --index-url pip povuče CUDA verziju od ~2.5 GB
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# iste verzije kao na laptopu gde su merenja rađena
RUN pip install ultralytics==8.4.203 onnxruntime==1.31.1 mediapipe==1.2.2 psutil websockets requests

# MediaPipe na Linux-u učitava EGL/GLES pri pravljenju detektora lica, čak i bez GPU-a
# (bez ovoga: "OSError: libEGL.so.1: cannot open shared object file")
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libgles2 \
 && rm -rf /var/lib/apt/lists/*

# Ultralytics pri učitavanju ONNX modela traži paket onnx i bez njega ga SAM skida sa interneta u toku rada.
# onnxslim treba samo setup_models.py (ONNX export).
RUN pip install onnx==1.23.2 onnxslim

# Težine modela nisu u gitu: pravi ih setup_models.py pri izgradnji (yolo11n*.pt sa Ultralytics GitHub-a -> ONNX,
# face_landmarker.task sa Google-a). Internet treba samo ovde, jednom; sloj ostaje u kešu dok se fajl ne promeni.
WORKDIR /app
COPY setup_models.py ./
RUN python setup_models.py && rm -f /app/*.pt

# U autu nema interneta: automatsko instaliranje i online provere su isključeni.
ENV YOLO_AUTOINSTALL=false YOLO_OFFLINE=true

COPY pipeline.py features.py scoring.py sender.py rivian_detector.py rois.json ./

ENTRYPOINT ["python"]
CMD ["rivian_detector.py"]
