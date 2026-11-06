#!/usr/bin/env bash
# Instalacija paketa i modela za risk_pipeline.py (Linux / macOS).
# Pokrenuti iz foldera gde su risk_pipeline.py i risk_config.json:
#   bash setup_models.sh               -> samo instalacija
#   bash setup_models.sh snimak.mp4    -> instalacija + test na jednom snimku
set -e
cd "$(dirname "$0")"

pip install opencv-python mediapipe numpy ultralytics onnx

mkdir -p models
[ -f models/face_landmarker.task ] || curl -L -o models/face_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
[ -f models/hand_landmarker.task ] || curl -L -o models/hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
if [ ! -f models/yolo11n_320.onnx ]; then
  python -c "from ultralytics import YOLO; YOLO('yolo11n.pt').export(format='onnx', imgsz=320)"
  mv yolo11n.onnx models/yolo11n_320.onnx
fi
ls -l models

if [ -n "$1" ]; then
  python risk_pipeline.py --video "$1" --show
fi
