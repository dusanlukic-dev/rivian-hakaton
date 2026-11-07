"""Kamera za probu na telefonu: svaka nova voznja iz aplikacije dobija sledeci klip, od pocetka.

    python rivian_model/klip_po_voznji.py                      # podrazumevani klipovi (kolaps + 3 bez kolapsa)
    python rivian_model/klip_po_voznji.py --klipovi 05_23_62_031246 05_23_62_022338 --port 8000
    .\\demo.ps1 -PoVoznji                                         # isto, pokrece ga demo.ps1 u svom prozoru

Kad voznja krene: pokrene tools/camera_stream.py sa sledecim klipom (u petlji). Kad se voznja zavrsi: ugasi kameru.

ZASTITA: koordinator prima vise kamera odjednom i mesa njihove frejmove (model tada vidi "dva vozaca").
Zato ovaj program ne krece ako je neka kamera vec povezana (npr. demo.ps1 pokrenut sa -Video), a pre svake voznje
ponovo proverava da nijedna druga kamera nije povezana. Svi klipovi moraju biti iz iste serije kamera (zona vozaca).
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(REPO, "backend", ".venv", "Scripts", "python.exe")
CAMERA = os.path.join(REPO, "tools", "camera_stream.py")
DATASET = r"C:\Users\PC\Downloads\Hackathon dataset 2026\Hackathon dataset 2026"
KLIPOVI = ["05_23_62_022338", "05_23_62_032409", "05_23_62_032617", "05_23_62_005853"]


def status(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/coordinator/status", timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


def other_cameras(port):
    s = status(port)
    return (s or {}).get("camera", {}).get("stream_clients", 0)


def stop(cam):
    if cam:
        cam.kill()
        cam.wait()


def main():
    ap = argparse.ArgumentParser(description="Svaka nova voznja dobija sledeci klip.")
    ap.add_argument("--klipovi", nargs="+", default=KLIPOVI)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--dataset", default=DATASET)
    a = ap.parse_args()

    serije = {k[:5] for k in a.klipovi}
    if len(serije) > 1:
        sys.exit(f"Klipovi su iz razlicitih serija kamera {sorted(serije)}: model ima jednu zonu vozaca po pokretanju.")
    for k in a.klipovi:
        if not os.path.exists(os.path.join(a.dataset, f"{k}_video_inCabin.mp4")):
            sys.exit(f"Nema klipa {k} u {a.dataset}")
    if status(a.port) is None:
        sys.exit(f"Koordinator ne odgovara na portu {a.port}. Prvo pokreni backend (demo.ps1).")
    n = other_cameras(a.port)
    if n:
        sys.exit(f"Vec je povezano kamera: {n} (verovatno demo.ps1 sa -Video ili -Webcam). Dve kamere se mesaju u "
                 f"koordinatoru. Ugasi tu kameru ili pokreni demo sa -PoVoznji umesto -Video.")

    print(f"Cekam voznje iz aplikacije (port {a.port}, serija {serije.pop()}). Redosled: {a.klipovi}", flush=True)
    try:
        loop(a)
    finally:
        stop(_cam[0])  # Ctrl+C ili greska: nasa kamera ne sme da ostane da radi


_cam = [None]


def loop(a):
    cam, aktivna, i = None, None, 0
    while True:
        _cam[0] = cam
        s = status(a.port) or {}
        t = s.get("trip_id")
        if t and t != aktivna:
            stop(cam)
            cam = None
            time.sleep(0.5)  # da se nasa stara kamera odjavi pre provere
            n = other_cameras(a.port)
            if n:
                print(f"[{time.strftime('%H:%M:%S')}] voznja {t[:8]}: VEC RADI DRUGA KAMERA ({n}), ne pokrecem klip "
                      f"da se frejmovi ne mesaju. Ugasi je pa pokreni novu voznju.", flush=True)
                aktivna = t
            elif i >= len(a.klipovi):
                print(f"[{time.strftime('%H:%M:%S')}] voznja {t[:8]}: nema vise klipova, kamera ugasena", flush=True)
                aktivna = t
            else:
                klip = a.klipovi[i]
                cam = subprocess.Popen(
                    [PY, CAMERA, "--url", f"ws://127.0.0.1:{a.port}/api/v1/camera/ws",
                     "--video", os.path.join(a.dataset, f"{klip}_video_inCabin.mp4")],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"[{time.strftime('%H:%M:%S')}] voznja {t[:8]} -> klip {i + 1}/{len(a.klipovi)}: {klip}",
                      flush=True)
                aktivna, i = t, i + 1
        elif not t and aktivna:
            stop(cam)
            cam = None
            print(f"[{time.strftime('%H:%M:%S')}] voznja {aktivna[:8]} zavrsena, kamera ugasena", flush=True)
            aktivna = None
        _cam[0] = cam
        time.sleep(0.3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
