#!/usr/bin/env bash
# Preuzimanje modela za risk_pipeline.py i model/worker.py (Linux / macOS).
#
# Modeli idu u notebooks/models/ (nije u gitu):
#   face_landmarker.task, hand_landmarker.task  - samo se preuzmu (curl, Python ne treba)
#   yolo11s_640.onnx                            - export iz ultralytics (treba ultralytics + onnx)
# yolo11s/640 jer nano/320 skoro ne vidi telefon na fisheye cabin kameri (risk_config.json: yolo_onnx,
# vidi .claude/knowledge/cv-pipeline.md).
#
# Pakete prvo instaliraj iz requirements.txt, u venv ili globalno:
#   python3 -m pip install -r requirements.txt
#
# Zatim pokreni iz bilo kog foldera:
#   bash setup_models.sh               # samo preuzme modele
#   bash setup_models.sh snimak.mp4    # preuzme modele i pusti test na snimku

set -eu

# Putanja do snimka se računa u odnosu na folder iz kog je skripta pozvana
VIDEO="${1:-}"
if [ -n "$VIDEO" ] && [ "${VIDEO#/}" = "$VIDEO" ]; then
    VIDEO="$PWD/$VIDEO"
fi

cd "$(dirname "$0")"

PY=""
# Python iz aktivnog venv-a, a ako ga nema, sistemski. Postavlja PY.
find_python() {
    [ -n "$PY" ] && return 0
    if command -v python3 >/dev/null 2>&1; then
        PY=python3
    elif command -v python >/dev/null 2>&1; then
        PY=python
    else
        echo "Greška: Python nije pronađen." >&2
        exit 1
    fi
    "$PY" -c "import sys; print('Python:', sys.executable)"
}

# Provera da su paketi iz requirements.txt instalirani baš za taj Python. Argument: moduli za import.
need_packages() {
    if ! "$PY" -c "import $1"; then
        echo >&2
        echo "Greška: nisu instalirani svi paketi za ovaj Python (treba: $1)." >&2
        echo "Instaliraj ih (u venv ili globalno):" >&2
        echo "  $PY -m pip install -r requirements.txt" >&2
        exit 1
    fi
}

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
echo "Modeli:"

download https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task \
    models/face_landmarker.task

download https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task \
    models/hand_landmarker.task

if [ -f models/yolo11s_640.onnx ]; then
    echo "  [ok] models/yolo11s_640.onnx već postoji"
else
    find_python
    need_packages "ultralytics, onnx"
    echo "  Export YOLO11s u ONNX (imgsz=640) ..."
    "$PY" -c "from pathlib import Path; from ultralytics import YOLO; Path(YOLO('models/yolo11s.pt').export(format='onnx', imgsz=640)).replace('models/yolo11s_640.onnx')"
fi

echo
echo "Instalirani modeli:"
ls -lh models

# Test na snimku ako je prosleđen argument
if [ -n "$VIDEO" ]; then
    find_python
    need_packages "cv2, mediapipe, numpy"
    echo
    echo "Test na snimku: $VIDEO"
    "$PY" risk_pipeline.py --video "$VIDEO" --show
fi

echo
echo "Gotovo! Pokretanje:"
echo "  python3 risk_pipeline.py --video snimak.mp4 --show"
if [ -n "${VIRTUAL_ENV:-}" ]; then
    echo "  (u novom terminalu prvo aktiviraj venv: source $VIRTUAL_ENV/bin/activate)"
fi
