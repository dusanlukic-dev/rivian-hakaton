"""Pravi fajlove koji nisu u gitu: yolo11n_640.onnx, yolo11n-pose_384.onnx, face_landmarker.task i (opciono)
warmup_frame.jpg.
    python setup_models.py
    python setup_models.py --warmup-from "<dataset>\\08_14_62_092916_video_inCabin.mp4"
Treba: pip install ultralytics onnx onnxslim (+ opencv-python za --warmup-from)
Ako download pada zbog SSL-a (antivirus koji pregleda HTTPS, npr. AVG), skini rucno curl-om pa pokreni ponovo.

warmup_frame.jpg = jedan frejm iz kabine sa licem vozaca, za zagrevanje modela pre prve voznje (rivian_detector.py).
Nije u gitu jer je iz dataseta hakatona (lica stvarnih ljudi). Bez njega model radi, samo su prve ~2 s voznje sporije.
"""
import argparse
import os
import urllib.request

from ultralytics import YOLO

HERE = os.path.dirname(os.path.abspath(__file__))
FACE_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"


def warmup_frame(clip, at_s=2.0, width=1280):
    """Frejm iz klipa (u sekundi at_s), smanjen na sirinu koju salje koordinator."""
    import cv2
    cap = cv2.VideoCapture(clip)
    cap.set(cv2.CAP_PROP_POS_MSEC, at_s * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"Ne mogu da procitam frejm iz {clip}")
    h, w = frame.shape[:2]
    frame = cv2.resize(frame, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
    out = os.path.join(HERE, "warmup_frame.jpg")
    cv2.imwrite(out, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return out


def main():
    ap = argparse.ArgumentParser(description="Modeli (i slika za zagrevanje) za rivian_model.")
    ap.add_argument("--warmup-from", help="klip iz dataseta iz kog se pravi warmup_frame.jpg (frejm u 2. sekundi)")
    a = ap.parse_args()

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
    if a.warmup_from:
        print("ok", warmup_frame(a.warmup_from))
    elif not os.path.exists(os.path.join(HERE, "warmup_frame.jpg")):
        print("nema warmup_frame.jpg: model radi i bez nje (dodaj --warmup-from <klip iz dataseta>)")


if __name__ == "__main__":
    main()
