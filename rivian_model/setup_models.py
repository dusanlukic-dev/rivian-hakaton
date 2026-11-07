"""Pravi fajlove modela koji nisu u gitu: yolo11n_640.onnx, yolo11n-pose_384.onnx i face_landmarker.task.
    python setup_models.py
Treba: ultralytics, onnx, onnxslim (requirements.txt). .pt modeli se skidaju sa Ultralytics GitHub-a.
Ako download pada zbog SSL-a (antivirus koji pregleda HTTPS, npr. AVG), skini rucno curl-om pa pokreni ponovo.

Zagrevanje vise ne treba sliku iz dataseta: rivian_detector.py se zagreva sivim frejmom pri pokretanju.
"""
import os
import urllib.request

from ultralytics import YOLO

HERE = os.path.dirname(os.path.abspath(__file__))
FACE_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"


def main():
    for name, imgsz in (("yolo11n", 640), ("yolo11n-pose", 384)):
        out = os.path.join(HERE, f"{name}_{imgsz}.onnx")
        if not os.path.exists(out):
            path = YOLO(os.path.join(HERE, name + ".pt")).export(format="onnx", imgsz=imgsz, simplify=True)
            os.replace(path, out)
        print("ok", out)
    face = os.path.join(HERE, "face_landmarker.task")
    if not os.path.exists(face):
        urllib.request.urlretrieve(FACE_URL, face)
    print("ok", face)


if __name__ == "__main__":
    main()
