#!/usr/bin/env bash
# Preuzimanje modela za risk_pipeline.py (Linux / macOS).
#
# Pakete prvo instaliraj iz requirements.txt, u venv ili globalno:
#   python3 -m pip install -r requirements.txt
#
# Zatim pokreni iz foldera gde su risk_pipeline.py i risk_config.json:
#   bash setup_models.sh               # samo preuzme modele
#   bash setup_models.sh snimak.mp4    # preuzme modele i pusti test na snimku

set -eu

# Putanja do snimka se računa u odnosu na folder iz kog je skripta pozvana
VIDEO="${1:-}"
if [ -n "$VIDEO" ] && [ "${VIDEO#/}" = "$VIDEO" ]; then
    VIDEO="$PWD/$VIDEO"
fi

cd "$(dirname "$0")"

# Koristi Python iz aktivnog venv-a, a ako ga nema, sistemski
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "Greška: Python nije pronađen." >&2
    exit 1
fi
"$PY" -c "import sys; print('Python:', sys.executable)"

# Provera da su paketi iz requirements.txt instalirani baš za taj Python
if ! "$PY" -c "import cv2, mediapipe, numpy, ultralytics, onnx"; then
    echo >&2
    echo "Greška: nisu instalirani svi paketi za ovaj Python." >&2
    echo "Instaliraj ih (u venv ili globalno):" >&2
    echo "  $PY -m pip install -r requirements.txt" >&2
    exit 1
fi

# Preuzima fajl samo ako već ne postoji. Ide preko .part fajla,
# da prekinuto ili neuspelo preuzimanje ne ostavi pokvaren model.
download() {
    local url="$1" out="$2"
    if [ -f "$out" ]; then
        echo "  [ok] $out već postoji"
        return 0
    fi
    echo "  Preuzimam $out ..."
    if ! curl -fL --retry 3 -o "$out.part" "$url"; then
        rm -f "$out.part"
        echo "Greška: preuzimanje nije uspelo: $url" >&2
        return 1
    fi
    mv "$out.part" "$out"
}

mkdir -p models
[ -f models/face_landmarker.task ] || curl -L -o models/face_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
[ -f models/hand_landmarker.task ] || curl -L -o models/hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
# yolo11s/640: nano/320 skoro ne vidi telefon na fisheye cabin kameri (vidi .claude/knowledge/cv-pipeline.md)
if [ ! -f models/yolo11s_640.onnx ]; then
  python -c "from ultralytics import YOLO; YOLO('yolo11s.pt').export(format='onnx', imgsz=640)"
  mv yolo11s.onnx models/yolo11s_640.onnx
fi
ls -l models

echo "Modeli:"

download https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task \
    models/face_landmarker.task

download https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task \
    models/hand_landmarker.task

if [ -f models/yolo11n_320.onnx ]; then
    echo "  [ok] models/yolo11n_320.onnx već postoji"
else
    echo "  Export YOLO11n u ONNX (imgsz=320) ..."
    "$PY" -c "from pathlib import Path; from ultralytics import YOLO; Path(YOLO('models/yolo11n.pt').export(format='onnx', imgsz=320)).replace('models/yolo11n_320.onnx')"
fi

echo
echo "Instalirani modeli:"
ls -lh models

# Test na snimku ako je prosleđen argument
if [ -n "$VIDEO" ]; then
    echo
    echo "Test na snimku: $VIDEO"
    "$PY" risk_pipeline.py --video "$VIDEO" --show
fi

echo
echo "Gotovo! Pokretanje:"
echo "  $PY risk_pipeline.py --video snimak.mp4 --show"
if [ -n "${VIRTUAL_ENV:-}" ]; then
    echo "  (u novom terminalu prvo aktiviraj venv: source $VIRTUAL_ENV/bin/activate)"
fi
