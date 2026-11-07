"""
test_rivian_detector.py - test našeg detektora BEZ njihovog backenda.

Lažni koordinator po istom protokolu kao rivian-hakaton/backend/app/coordinator/services/model_link.py:
    detektor se javi (hello) -> reset -> frejmovi (zaglavlje {type, id, t, trip_id} + JPEG 1280 px) -> detection
    -> idle
Frejm po frejm (jedan u letu), 10 u sekundi videa (svaki 3. od 30). Na kraju se od dobijenih dokaza izračuna
skor našim scoring.py i uporedi sa onim što pipeline.py daje na istom klipu.

    python test_rivian_detector.py 08_14_62_092916
    python test_rivian_detector.py 05_23_62_031246 --port 8766
    python test_rivian_detector.py 08_14_62_092916 --external     (detektor se javlja spolja, npr. iz Docker-a:
        docker run --rm rivian-model rivian_detector.py --coordinator ws://host.docker.internal:8766/api/v1/model/ws)
"""
import argparse
import asyncio
import json
import os
import statistics
import struct
import subprocess
import sys
import tempfile
import time

import cv2
from websockets.asyncio.server import serve

from pipeline import DATA  # $DATASET_DIR, inace ../../dataset, inace Dusanov put
from rivian_detector import CATEGORY_MAP
from scoring import DriverScorer

HERE = os.path.dirname(os.path.abspath(__file__))
EXPECTED = {    # pipeline.py na punoj rezoluciji (ATRIBUTI.md)
    "08_14_62_092916": "39 red, phone 12.5-24.2",
    "08_14_62_084339": "29 red, phone + look_away od ~10 s",
    "08_14_62_085956": "100 green, bez dogadjaja",
    "05_23_62_031246": "0 red + hitan alarm, collapse 11.0-29.9",
}
_HEADER = struct.Struct("<I")


def pack_frame(header, jpeg):
    raw = json.dumps(header, separators=(",", ":")).encode()
    return _HEADER.pack(len(raw)) + raw + jpeg


def camera_frames(path, step=3, width=1280, quality=90):
    """Kao tools/camera_stream.py: 10 fps, 1280 px širine, JPEG."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    i = 0
    while cap.grab():
        if i % step == 0:
            _, f = cap.retrieve()
            f = cv2.resize(f, (width, int(f.shape[0] * width / f.shape[1])), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, quality])
            yield i, round(i / fps, 3), buf.tobytes()
        i += 1
    cap.release()


async def run(clip, port, external=False, host="127.0.0.1"):
    finished = asyncio.get_running_loop().create_future()
    results, hello = [], {}

    async def coordinator(ws):
        hello.update(json.loads(await ws.recv()))
        trip = f"test-{clip}"
        await ws.send(json.dumps({"type": "reset", "trip_id": trip}))
        for fid, t, jpeg in camera_frames(os.path.join(DATA, clip + "_video_inCabin.mp4")):
            sent = time.perf_counter()
            await ws.send(pack_frame({"type": "frame", "id": fid, "t": t, "trip_id": trip}, jpeg))
            while True:                                  # jedan frejm u letu: čekamo odgovor baš za njega
                msg = json.loads(await asyncio.wait_for(ws.recv(), 30))
                if msg.get("id") == fid and msg.get("type") in ("detection", "error"):
                    break
            results.append((t, msg, (time.perf_counter() - sent) * 1000, len(jpeg)))
        await ws.send(json.dumps({"type": "idle"}))
        if not finished.done():
            finished.set_result(True)

    log_path = os.path.join(tempfile.gettempdir(), f"rivian_detector_{clip}.log")
    async with serve(coordinator, host, port, max_size=None):
        if external:                       # detektor se pokreće spolja (npr. Docker kontejner)
            print(f"cekam detektor na ws://{host}:{port}/api/v1/model/ws ...", flush=True)
            await asyncio.wait_for(finished, 900)
            return hello, results, None
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(
                [sys.executable, os.path.join(HERE, "rivian_detector.py"),
                 "--coordinator", f"ws://127.0.0.1:{port}/api/v1/model/ws", "--camera", clip[:5]],
                cwd=HERE, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            try:
                await asyncio.wait_for(finished, 600)
            finally:
                proc.terminate()
                proc.wait(15)
    return hello, results, log_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--external", action="store_true", help="ne pokreci detektor; cekaj da se javi spolja (Docker)")
    ap.add_argument("--host", default="127.0.0.1", help="adresa na kojoj lazni koordinator slusa")
    a = ap.parse_args()
    start = time.perf_counter()
    hello, results, log_path = asyncio.run(run(a.clip, a.port, a.external, a.host))

    inv = {v: k for k, v in CATEGORY_MAP.items()}
    sc = DriverScorer(a.clip)
    errors, worker_ms, round_ms, sizes, calibrated_at = 0, [], [], [], None
    for t, msg, rt, size in results:
        if msg["type"] != "detection":
            errors += 1
            continue
        sc.update(t, {inv[c]: p for c, p in msg["evidence"].items() if c in inv})
        worker_ms.append(msg["ms"])
        round_ms.append(rt)
        sizes.append(size)
        if calibrated_at is None and msg.get("perception", {}).get("calibrated"):
            calibrated_at = t
    r = sc.finish()
    ev = ", ".join(f'{e["type"]} {e["start"]}-{e["end"]}' for e in r["events"]) or "-"
    p95 = lambda v: sorted(v)[int(0.95 * (len(v) - 1))]
    print(f"detektor: {hello.get('worker')} v{hello.get('version')}, kategorije {hello.get('categories')}")
    print(f"frejmova: {len(results)}, gresaka: {errors}, JPEG prosek {statistics.mean(sizes) / 1024:.0f} KB")
    print(f"vreme u detektoru: medijana {statistics.median(worker_ms):.1f} ms, p95 {p95(worker_ms):.1f} ms | "
          f"ceo krug (slanje + detekcija + odgovor): medijana {statistics.median(round_ms):.1f} ms")
    print(f"kalibracija pogleda gotova u t = {calibrated_at} s")
    print(f"skor iz dokaza (nas scoring.py): {r['score']} {r['color']}, emergency={r['emergency']} | {ev}")
    print(f"ocekivano (pipeline.py, puna rezolucija): {EXPECTED.get(a.clip, '?')}")
    print(f"ukupno {time.perf_counter() - start:.0f} s | log detektora: {log_path}")


if __name__ == "__main__":
    main()
