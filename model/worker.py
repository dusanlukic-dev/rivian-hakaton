"""Model worker: camera frames in, detections out. Its own process and environment (later its own container).

It dials into the coordinator and stays connected (reconnecting by itself):

    coordinator ──frame (JPEG + {id, t, trip_id})──► worker: detectors ──► evidence p_i per category
    coordinator ◄──{"type": "detection", "id", "evidence", "perception", "ms"}──┘

Protocol: backend/app/coordinator/services/model_link.py. The worker only *detects*. Everything after the
evidence (smoothing, durations, risk, alert, the 0-100 score, the car's reaction) is the coordinator's job.

    python model/worker.py                 # the CV team's detectors: notebooks/risk_pipeline.py (MediaPipe + YOLO)
    python model/worker.py --fake          # scripted detections, no CV packages: test the pipeline, demo without a camera
    python model/worker.py --coordinator ws://10.0.0.5:8000/api/v1/model/ws

The CV code is used as it is: FacePerception, HandPerception, ObjectPerception and FeatureExtractor from
notebooks/risk_pipeline.py, thresholds from notebooks/risk_config.json, models from notebooks/models/
(`notebooks/setup_models.*`). Without the YOLO model the phone is seen only through the "looking at the lap"
cue. Setup: model/README.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from websockets.asyncio.client import connect

REPO = Path(__file__).resolve().parents[1]
NOTEBOOKS = REPO / "notebooks"
DEFAULT_COORDINATOR = os.environ.get("COORDINATOR_URL", "ws://127.0.0.1:8000/api/v1/model/ws")
VERSION = "1.0"
_HEADER = struct.Struct("<I")


def unpack_frame(data: bytes) -> tuple[dict, bytes]:
    (size,) = _HEADER.unpack_from(data)
    start = _HEADER.size
    return json.loads(data[start : start + size]), data[start + size :]


class CvDetector:
    """The CV team's perception + FeatureExtractor, one frame at a time (the body of risk_pipeline.run())."""

    name = "cv-pipeline"

    def __init__(self, config_path: Path) -> None:
        sys.path.insert(0, str(NOTEBOOKS))
        import cv2
        import numpy as np
        import risk_pipeline as rp

        self.cv2, self.np, self.rp = cv2, np, rp
        self.cfg = json.loads(config_path.read_text(encoding="utf-8"))
        vc, mc = self.cfg["video"], self.cfg["models"]

        def model_path(key: str) -> Path:
            path = Path(mc[key])
            return path if path.is_absolute() else NOTEBOOKS / path

        self.face = rp.FacePerception(str(model_path("face_landmarker")), mc.get("face_num", 2),
                                      mc.get("face_min_conf", 0.4), vc.get("driver_side", "right"))
        self.hands = rp.HandPerception(str(model_path("hand_landmarker")), mc.get("hands_num", 4))
        yolo = model_path("yolo_onnx")
        if yolo.exists():
            self.objects = rp.ObjectPerception(str(yolo), mc["yolo_input"], mc["yolo_conf"])
        else:
            self.objects = None
            print(f"No YOLO model at {yolo}: the phone is seen only through 'looking at the lap' (setup_models)")
        self.categories = list(self.cfg["categories"])
        self._last_ts = -1
        self._base_ms = 0
        self.reset()

    def reset(self) -> None:
        """New trip: fresh feature state (head baseline calibration, PERCLOS, phone memory)."""
        self.fx = self.rp.FeatureExtractor(self.cfg)
        self.k = -1
        self.held = {"face": (None, -1e9), "hands": (None, -1e9), "objects": (None, -1e9)}
        self._base_ms = self._last_ts + 1  # MediaPipe VIDEO mode needs ever-increasing timestamps

    def detect(self, jpeg: bytes, t: float) -> tuple[dict, dict]:
        cv2, np, rp = self.cv2, self.np, self.rp
        vc, sc = self.cfg["video"], self.cfg["schedule"]
        src = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if src is None:
            raise ValueError("not a decodable JPEG")
        self.k += 1
        k, roi, head_roi = self.k, vc["driver_roi"], vc["head_roi"]
        h, w = src.shape[:2]
        frame = cv2.resize(src, (vc["input_width"], int(h * vc["input_width"] / w)))
        ts_ms = max(self._base_ms + int(t * 1000), self._last_ts + 1)
        self._last_ts = ts_ms

        def rgb(img):
            return np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

        if k % sc["face_every_n"] == 0:
            self.held["face"] = (self.face(rgb(rp._crop(frame, head_roi)), ts_ms, head_roi), t)
        if k % sc["hands_every_n"] == 0:
            self.held["hands"] = (self.hands(rgb(rp._crop(frame, roi)), ts_ms, roi), t)
        if self.objects is not None and k % sc["objects_every_n"] == 0:
            yolo_src = src if vc.get("yolo_full_res", True) else frame  # YOLO on the full-resolution crop
            self.held["objects"] = (self.objects(rp._crop(yolo_src, roi), roi), t)

        def fresh(key):
            result, at = self.held[key]
            return result if t - at <= sc["max_result_age_s"] else None

        evidence, perception = self.fx.update(t, fresh("face"), fresh("hands"), fresh("objects"))
        slim = {key: perception.get(key) for key in (
            "face_found", "yaw", "pitch", "eye_closure", "gaze_down", "perclos",
            "hands_detected", "hands_on_wheel", "phone_now", "phone_held", "baseline_status",
        ) if key in perception}
        return {name: round(float(p), 4) for name, p in evidence.items()}, slim


class FakeDetector:
    """Scripted detections on a 60 s loop, so the whole pipeline works without a camera or CV packages."""

    name = "fake"
    categories = ["phone_use", "eyes_off_road", "hands_off_wheel", "eating_drinking", "drowsiness", "eyes_closed"]
    # (from s, to s, evidence). The coordinator's mock speed decides whether it is driving at that moment.
    SCRIPT = [
        (14, 20, {"phone_use": 0.9, "eyes_off_road": 0.85}),     # texting
        (28, 31, {"eyes_off_road": 0.9}),                        # long look away
        (38, 41, {"eyes_closed": 0.95}),                         # microsleep
        (48, 52, {"hands_off_wheel": 0.9}),                      # no hand on the wheel
    ]

    def __init__(self, seed: int = 7) -> None:
        self.rng = random.Random(seed)

    def reset(self) -> None:
        pass

    def detect(self, jpeg: bytes, t: float) -> tuple[dict, dict]:
        phase = t % 60.0
        evidence = {name: round(0.04 + 0.03 * self.rng.random(), 4) for name in self.categories}
        for start, end, values in self.SCRIPT:
            if start <= phase < end:
                ramp = min(1.0, (phase - start) / 0.4, (end - phase) / 0.4)  # no instant on/off
                for name, p in values.items():
                    evidence[name] = round(max(evidence[name], p * ramp + 0.04 * math.sin(7 * t)), 4)
        return evidence, {"script_t": round(phase, 2)}


async def serve(args: argparse.Namespace, detector) -> None:
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="detect")  # detectors aren't thread-safe
    delay = 1.0
    while True:
        try:
            async with connect(args.coordinator, max_size=None, ping_interval=20) as ws:
                await ws.send(json.dumps({
                    "type": "hello", "worker": detector.name, "version": VERSION, "categories": detector.categories,
                }))
                print(f"Connected to {args.coordinator} as '{detector.name}'")
                delay, done, busy, since = 1.0, 0, 0.0, time.monotonic()
                async for message in ws:
                    if isinstance(message, str):
                        data = json.loads(message)
                        if data.get("type") == "reset":
                            await loop.run_in_executor(executor, detector.reset)
                            print(f"New trip {data.get('trip_id')}: detectors reset")
                        elif data.get("type") == "idle":
                            print("Trip over: waiting for the next one")
                        continue
                    header, jpeg = unpack_frame(message)
                    started = time.perf_counter()
                    try:
                        evidence, perception = await loop.run_in_executor(executor, detector.detect, jpeg, header["t"])
                    except Exception as e:  # one bad frame must not stop the worker
                        await ws.send(json.dumps({"type": "error", "id": header["id"], "message": str(e)[:200]}))
                        continue
                    ms = (time.perf_counter() - started) * 1000
                    await ws.send(json.dumps({
                        "type": "detection", "id": header["id"], "t": header["t"], "trip_id": header.get("trip_id"),
                        "evidence": evidence, "perception": perception, "ms": round(ms, 1),
                    }))
                    done, busy = done + 1, busy + ms
                    if time.monotonic() - since >= 10:
                        print(f"  {done / (time.monotonic() - since):4.1f} frames/s, {busy / done:5.1f} ms per frame")
                        done, busy, since = 0, 0.0, time.monotonic()
        except Exception as e:
            print(f"Coordinator unreachable ({type(e).__name__}: {e}); retrying in {delay:.0f} s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10.0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Driver-monitoring model worker for the coordinator.")
    parser.add_argument("--coordinator", default=DEFAULT_COORDINATOR, help="the coordinator's /model/ws URL")
    parser.add_argument("--fake", action="store_true", help="scripted detections (no CV packages needed)")
    parser.add_argument("--config", type=Path, default=NOTEBOOKS / "risk_config.json")
    args = parser.parse_args()
    detector = FakeDetector() if args.fake else CvDetector(args.config)
    try:
        asyncio.run(serve(args, detector))
    except KeyboardInterrupt:
        pass
