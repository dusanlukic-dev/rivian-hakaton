"""
rivian_detector.py - NAŠ model kao detektor za koordinator (protokol iz rivian-hakaton/model/worker.py).

Isti oblik kao CvDetector u njihovom worker.py: name, categories, reset(), detect(jpeg, t) -> (evidence, perception).
Model samo kaže šta vidi na frejmu (dokaz 0-1 po kategoriji). Glađenje, trajanje, alarm, skor 0-100 i reakciju
kola računa koordinator (njihov RiskEngine + scoring).

Mapiranje naših signala na njihove kategorije:
    phone     -> phone_use
    look_away -> eyes_off_road
    drowsy    -> eyes_closed
    collapse  -> collapse      (NOVA kategorija: koordinator je koristi tek kad se doda u risk_config.json)

Pokretanje (samostalno, bez ikakve izmene njihovog repoa):
    python rivian_detector.py                          # javlja se na ws://127.0.0.1:8000/api/v1/model/ws
    python rivian_detector.py --camera 05_23           # zona vozača za drugu seriju kamera (podrazumevano 08_14)
    python rivian_detector.py --coordinator ws://10.0.0.5:8000/api/v1/model/ws
U njihovom repou se klasa RivianDetector samo doda u model/worker.py pored CvDetector i FakeDetector.
Test bez njihovog backenda: python test_rivian_detector.py 08_14_62_092916
"""
import argparse
import asyncio
import json
import os
import struct
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

import pipeline as P
from features import DriverLogic, Pose, phone_ok

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = "1.0"
CATEGORY_MAP = {"phone": "phone_use", "look_away": "eyes_off_road", "drowsy": "eyes_closed", "collapse": "collapse"}
REF_W, REF_H = 1920, 1536          # rois.json je u pikselima punog frejma kamere; koordinator šalje manji (1280 px)
DEFAULT_COORDINATOR = os.environ.get("COORDINATOR_URL", "ws://127.0.0.1:8000/api/v1/model/ws")


class RivianDetector:
    """Naš model (yolo11n telefon + yolo11n-pose + MediaPipe lice + features.DriverLogic), jedan frejm po pozivu."""

    name = "rivian-pose"
    categories = list(CATEGORY_MAP.values())

    def __init__(self, camera="08_14", phone_every=2, warmup_image=None):
        self.camera, self.phone_every = camera, phone_every
        self.models = P.Models("onnx", 640, 384)
        self.roi_ref = json.load(open(P.ROI_FILE))[camera]
        self.pool = ThreadPoolExecutor(1, thread_name_prefix="phone")   # telefon-YOLO paralelno, kao u pipeline.py
        self.reset()
        img = warmup_image or os.path.join(HERE, "warmup_frame.jpg")
        if os.path.exists(img):                    # zagrevanje odmah pri pokretanju, pre prve vožnje (~2 s)
            frame = cv2.imread(img)
            self.models.warmup(frame, self._roi(frame))

    def _roi(self, frame):
        """Zona vozača skalirana na veličinu frejma koji je stigao (npr. 1280x1024 umesto 1920x1536)."""
        h, w = frame.shape[:2]
        x, y, rw, rh = self.roi_ref
        sx, sy = w / REF_W, h / REF_H
        return [int(x * sx), int(y * sy), int(rw * sx), int(rh * sy)]

    def reset(self):
        """Nova vožnja: nova kalibracija pogleda, prazna memorija telefona i pokreta."""
        self.logic = DriverLogic(self.camera)
        self.n, self.phones, self.fut = 0, [], None

    def detect(self, jpeg, t):
        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("not a decodable JPEG")
        x, y, w, h = self._roi(frame)
        crop = frame[y:y + h, x:x + w]
        if self.n % self.phone_every == 0:         # telefon na svaki 2. frejm, rezultat prethodnog pokretanja
            if self.fut is not None:
                self.phones = self.fut.result()
            self.fut = self.pool.submit(P.run_phone, self.models, crop.copy(), x, y)
        self.n += 1
        kp = P.run_pose(self.models, crop, x, y)
        face = P.run_face(self.models, frame, Pose(kp) if kp else None)
        probs, sig, pose, face = self.logic.update(t, kp, self.phones, face)
        evidence = {CATEGORY_MAP[k]: round(float(v), 4) for k, v in probs.items()}
        perception = {
            "pose_found": kp is not None,
            "face_found": face is not None,
            "yaw": round(face["yaw"], 1) if face else None,
            "pitch": round(face["pitch"], 1) if face else None,
            "eye_closure": round((face["blinkL"] + face["blinkR"]) / 2, 3) if face else None,
            "phone_box": any(phone_ok(p, pose) for p in self.phones) if pose else False,
            "phone_confirmed": bool(sig["phone_confirmed"]),
            "calibrated": self.logic.calib.neutral is not None,
            "motion": round(sig["motion"], 3),
        }
        return evidence, perception

    def close(self):
        self.pool.shutdown()
        self.models.close()


# ---------- veza sa koordinatorom: isti protokol kao serve() u njihovom model/worker.py ----------
_HEADER = struct.Struct("<I")


def unpack_frame(data):
    (size,) = _HEADER.unpack_from(data)
    start = _HEADER.size
    return json.loads(data[start:start + size]), data[start + size:]


async def serve(url, detector):
    from websockets.asyncio.client import connect
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="detect")
    delay = 1.0
    while True:
        try:
            async with connect(url, max_size=None, ping_interval=20) as ws:
                await ws.send(json.dumps({"type": "hello", "worker": detector.name, "version": VERSION,
                                          "categories": detector.categories}))
                print(f"Povezan na {url} kao '{detector.name}'", flush=True)
                delay, done, busy, since = 1.0, 0, 0.0, time.monotonic()
                async for message in ws:
                    if isinstance(message, str):
                        data = json.loads(message)
                        if data.get("type") == "reset":
                            await loop.run_in_executor(executor, detector.reset)
                            print(f"Nova voznja {data.get('trip_id')}: detektori ispocetka", flush=True)
                        elif data.get("type") == "idle":
                            print("Voznja gotova: cekam sledecu", flush=True)
                        continue
                    header, jpeg = unpack_frame(message)
                    started = time.perf_counter()
                    try:
                        evidence, perception = await loop.run_in_executor(executor, detector.detect, jpeg, header["t"])
                    except Exception as e:                       # jedan los frejm ne sme da zaustavi model
                        await ws.send(json.dumps({"type": "error", "id": header["id"], "message": str(e)[:200]}))
                        continue
                    ms = (time.perf_counter() - started) * 1000
                    await ws.send(json.dumps({
                        "type": "detection", "id": header["id"], "t": header["t"], "trip_id": header.get("trip_id"),
                        "evidence": evidence, "perception": perception, "ms": round(ms, 1)}))
                    done, busy = done + 1, busy + ms
                    if time.monotonic() - since >= 10:
                        print(f"  {done / (time.monotonic() - since):4.1f} frejmova/s, {busy / done:5.1f} ms po frejmu",
                              flush=True)
                        done, busy, since = 0, 0.0, time.monotonic()
        except Exception as e:
            print(f"Koordinator nedostupan ({type(e).__name__}: {e}); novi pokusaj za {delay:.0f} s", flush=True)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10.0)


def main():
    ap = argparse.ArgumentParser(description="Nas model (rivian-pose) kao detektor za koordinator.")
    ap.add_argument("--coordinator", default=DEFAULT_COORDINATOR, help="koordinatorov /model/ws URL")
    ap.add_argument("--camera", default="08_14", choices=["08_14", "05_23"], help="serija kamere (zona vozaca)")
    ap.add_argument("--phone-every", type=int, default=2)
    a = ap.parse_args()
    detector = RivianDetector(a.camera, a.phone_every)
    try:
        asyncio.run(serve(a.coordinator, detector))
    except KeyboardInterrupt:
        pass
    finally:
        detector.close()


if __name__ == "__main__":
    main()
