@echo off
REM Instalacija paketa i modela za risk_pipeline.py (Windows).
REM Pokrenuti iz foldera gde su risk_pipeline.py i risk_config.json:
REM   setup_models.bat               -> samo instalacija
REM   setup_models.bat snimak.mp4    -> instalacija + test na jednom snimku
cd /d "%~dp0"

pip install opencv-python mediapipe numpy ultralytics onnx || goto :err

if not exist models mkdir models
if not exist models\face_landmarker.task curl -L -o models\face_landmarker.task https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
if not exist models\hand_landmarker.task curl -L -o models\hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
if not exist models\yolo11n_320.onnx (
  python -c "from ultralytics import YOLO; YOLO('yolo11n.pt').export(format='onnx', imgsz=320)" || goto :err
  move yolo11n.onnx models\yolo11n_320.onnx
)
dir models

if not "%~1"=="" python risk_pipeline.py --video "%~1" --show
goto :eof

:err
echo Greska tokom instalacije.
exit /b 1