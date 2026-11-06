"""Bridge between the camera models (YOLO / MediaPipe / OpenCV) and the backend.

Standard library only (OpenCV just to JPEG-encode numpy frames). Keep it next to the notebooks and:

    from safety_client import SafetyClient

    client = SafetyClient()  # backend running on the same laptop
    # inside the camera loop - calling both every frame is fine, they throttle themselves:
    client.send_frame(record)       # record = the dict you write to frames.jsonl (~2/s)
    client.send_video_frame(frame)  # the BGR frame from OpenCV (~8/s), for the dangerous-moment images

The backend maps the record's active categories to its labels (phone_use -> looking_at_phone...)
and forwards risk / alert / categories to the app. `perception` (raw detector output) is dropped
here; the app doesn't need it. Don't send a speed: the camera doesn't know it, and the backend
has its own (a mocked drive, or the phone's GPS). If you only have labels, use
`client.send({"looking_at_phone"})` with the names in BEHAVIORS.

Video frames go to the coordinator's video cache (5 min). Every 2 s section that was dangerous gets the
image of its riskiest frame in the driver's report. The newer path, where the coordinator sends camera
frames to a model worker itself, is tools/camera_stream.py + model/worker.py (docs/ARCHITECTURE.md).

Run this file directly to drive the backend without any models (useful for the app team):

    python safety_client.py                          # simulated drive through every level
    python safety_client.py --interval 0.3           # faster than real time
    python safety_client.py --video 0                # ...streaming the webcam: dangerous moments get images
    python safety_client.py --backend-speed          # speed from the backend's mock drive
    python safety_client.py --replay frames.jsonl    # replay a recorded model run
    python safety_client.py --replay frames.jsonl --speedup 2 --speed-kmh 90 --video run.mp4
"""

import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

BEHAVIORS = frozenset({
    "looking_at_phone",  # gleda u telefon
    "looking_behind",    # gleda iza sebe
    "turning_around",    # okreće se (telom)
    "hands_off_wheel",   # ruke van volana
    "drowsy",            # pospan
    "eyes_off_road",     # pogled van puta
})


def _jsonable(value: Any) -> Any:
    """Lets the models pass numpy numbers and arrays straight in."""
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class SafetyClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000/api/v1",
        min_interval_s: float = 0.5,
        timeout_s: float = 2.0,
        video_fps: float = 8.0,
        jpeg_quality: int = 70,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self.video_interval_s = 1.0 / video_fps if video_fps > 0 else 0.0
        self.jpeg_quality = jpeg_quality
        self._last_sent = float("-inf")
        self._last_video = float("-inf")

    def send_frame(
        self, record: dict, speed_kmh: float | None = None, timestamp: datetime | None = None
    ) -> dict | None:
        """Report one model record (a line of frames.jsonl), unchanged.

        Leave `speed_kmh` out (the backend provides the speed); pass it only to force a value.
        Returns the new trip state, or None if the call was throttled, no trip is active
        yet, or the backend is unreachable (so a hiccup never kills the camera loop).
        """
        frame = {key: value for key, value in record.items() if key != "perception"}
        return self._send_tick({"frame": frame}, speed_kmh, timestamp)

    def send(
        self, behaviors: Iterable[str], speed_kmh: float | None = None, timestamp: datetime | None = None
    ) -> dict | None:
        """Report backend labels directly (see BEHAVIORS). Same return value as send_frame."""
        behaviors = set(behaviors)
        unknown = behaviors - BEHAVIORS
        if unknown:
            raise ValueError(f"Unknown behaviors {sorted(unknown)}; use one of {sorted(BEHAVIORS)}")
        return self._send_tick({"behaviors": sorted(behaviors)}, speed_kmh, timestamp)

    def send_video_frame(self, image: Any) -> bool:
        """Stream one camera frame for the dangerous-moment images (throttles itself to `video_fps`).

        `image` is a BGR numpy frame as OpenCV reads it, or JPEG bytes. Returns True if the backend
        took it. Never raises on network trouble, so it can't kill the camera loop.
        """
        now = time.monotonic()
        if now - self._last_video < self.video_interval_s:
            return False
        self._last_video = now
        if isinstance(image, (bytes, bytearray, memoryview)):
            jpeg = bytes(image)
        else:
            import cv2  # only needed for numpy frames

            ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            if not ok:
                return False
            jpeg = buffer.tobytes()
        request = urllib.request.Request(
            self.base_url + "/video/frames", data=jpeg, headers={"Content-Type": "image/jpeg"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s):
                return True
        except OSError:  # backend down, no active trip yet (409)...
            return False

    def start_trip(self, driver_id: str, emergency_contact: dict | None = None) -> dict:
        return self._post("/trips", {"driver_id": driver_id, "emergency_contact": emergency_contact})

    def end_trip(self, trip_id: str) -> dict:
        return self._post(f"/trips/{trip_id}/end")

    def trip_moments(self, trip_id: str) -> list[dict]:
        """Dangerous moments of the drive report, with image URLs. Empty if storage is off or down."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/trips/{trip_id}/report", timeout=30) as response:
                return json.load(response)["moments"]
        except urllib.error.HTTPError as e:
            if e.code in (404, 503):
                return []
            raise

    def _send_tick(self, payload: dict, speed_kmh: float | None, timestamp: datetime | None) -> dict | None:
        now = time.monotonic()
        if now - self._last_sent < self.min_interval_s:
            return None
        self._last_sent = now

        # Local time with offset - the backend uses the hour for night penalties.
        body = {"timestamp": (timestamp or datetime.now().astimezone()).isoformat(), **payload}
        if speed_kmh is not None:
            body["speed_kmh"] = speed_kmh
        try:
            return self._post("/telemetry", body)
        except urllib.error.HTTPError as e:
            if e.code == 409:  # no active trip - the app hasn't started one yet
                return None
            raise
        except urllib.error.URLError:
            return None

    def _post(self, path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body, default=_jsonable).encode() if body is not None else b"",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            return json.load(response)


# (seconds, speed_kmh, behaviors) - walks through every safety level.
DEMO_DRIVE = [
    (10, 50, []),                                  # safe
    (8, 50, ["hands_off_wheel"]),                  # -> caution
    (10, 50, []),
    (5, 50, ["looking_at_phone"]),                 # -> warning
    (10, 50, []),
    (2, 80, ["looking_behind", "turning_around"]), # -> high risk
    (5, 80, []),
    (2, 60, ["looking_at_phone"]),                 # -> critical
    (5, 120, []),
    (3, 130, ["drowsy"]),                          # -> emergency
    (10, 0, ["looking_at_phone"]),                 # stopped at a light: no penalty
    (40, 60, []),
]


def _stream_video(client: SafetyClient, source: str, stop: threading.Event) -> None:
    """Plays a webcam (index) or a video file (looped, real time) into the backend."""
    import cv2

    live = source.isdigit()
    capture = cv2.VideoCapture(int(source) if live else source)
    if not capture.isOpened():
        print(f"Can't open video source {source!r}; driving without video")
        return
    frame_s = 1.0 / (capture.get(cv2.CAP_PROP_FPS) or 30.0)
    while not stop.is_set():
        ok, frame = capture.read()
        if not ok:
            if live:
                break
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        client.send_video_frame(frame)
        if not live:
            time.sleep(frame_s)
    capture.release()


@contextmanager
def _video(base_url: str, source: str | None) -> Iterator[None]:
    """Streams `source` in the background while the drive runs (needs OpenCV)."""
    if not source:
        yield
        return
    try:
        import cv2  # noqa: F401
    except ImportError:
        raise SystemExit("--video needs OpenCV: pip install opencv-python") from None
    stop = threading.Event()
    thread = threading.Thread(target=_stream_video, args=(SafetyClient(base_url), source, stop), daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)


def _print_state(seen: str, state: dict) -> None:
    r = state["response"]
    camera = state.get("camera") or {}
    model = f"  model={camera.get('alert')}/{camera.get('risk')}" if camera else ""
    print(
        f"{state.get('speed_kmh', 0):>5} km/h {state.get('speed_source') or '':<9} {seen or '-':<28} "
        f"score={state['score']:>5}  {state['level']:<10} light={r['dashboard_light']:<12} "
        f"vibrate={r['vibrate_seat']!s:<5} sound={r['sound']}{model}"
    )


def _print_summary(client: SafetyClient, summary: dict) -> None:
    print(f"\nFinal score {summary['final_score']} (avg {summary['average_score']}, min {summary['min_score']})")
    for b in summary["behaviors"]:
        print(f"  {b['behavior']}: {b['occurrences']}x, {b['total_seconds']} s - {b['tip']}")
    moments = sorted(client.trip_moments(summary["trip_id"]), key=lambda m: m["score_drop"], reverse=True)
    if moments:
        print(f"\nDangerous moments: {len(moments)} (worst first)")
        for m in moments[:5]:
            what = ", ".join(m["behaviors"]) or ", ".join(m["rules_triggered"]) or "model alarm"
            print(
                f"  t={m['t_start']:>6.1f} s  {m['duration_s']:>4} s  {m['danger']:<9} score -{m['score_drop']:<5} {what}"
                f"  {m['image_url'] or '(no image)'}"
            )


def run_demo(base_url: str, interval_s: float, backend_speed: bool, video: str | None) -> None:
    client = SafetyClient(base_url, min_interval_s=0)
    trip = client.start_trip("demo-driver", {"name": "Demo Contact", "phone": "+381600000000"})
    print(f"Started trip {trip['trip_id']}")

    ts = datetime.now().astimezone()
    with _video(base_url, video):
        for seconds, speed, behaviors in DEMO_DRIVE:
            for _ in range(seconds):
                ts += timedelta(seconds=1)  # simulated clock, so --interval can run faster than real time
                state = client.send(behaviors, None if backend_speed else speed, timestamp=ts)
                if state is None:
                    raise SystemExit("Backend unreachable or trip ended - is the server running?")
                _print_state(",".join(behaviors), state)
                time.sleep(interval_s)

    _print_summary(client, client.end_trip(trip["trip_id"]))


def run_replay(
    base_url: str, path: str, speed_kmh: float | None, speedup: float, step_s: float, video: str | None
) -> None:
    """Replay a recorded frames.jsonl as if the camera were live, paced by each record's `t`."""
    client = SafetyClient(base_url, min_interval_s=0)  # throttled below on the recording's clock
    trip = client.start_trip("replay-driver", {"name": "Demo Contact", "phone": "+381600000000"})
    print(f"Started trip {trip['trip_id']}, replaying {path}")

    start = datetime.now().astimezone()
    last_t: float | None = None
    with _video(base_url, video), open(path, encoding="utf-8") as lines:
        for line in lines:
            if not line.strip():
                continue
            record = json.loads(line)
            t = float(record.get("t") or 0.0)
            if last_t is not None:
                if t - last_t < step_s:
                    continue
                time.sleep((t - last_t) / speedup)
            last_t = t

            state = client.send_frame(record, speed_kmh, timestamp=start + timedelta(seconds=t))
            if state is None:
                raise SystemExit("Backend unreachable or trip ended - is the server running?")
            active = [name for name, c in (record.get("categories") or {}).items() if c.get("active")]
            _print_state(",".join(active), state)

    _print_summary(client, client.end_trip(trip["trip_id"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate or replay a drive against the backend.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--interval", type=float, default=1.0, help="demo: real seconds between ticks")
    parser.add_argument(
        "--backend-speed", action="store_true",
        help="demo: send no speed, so the backend's mock drive decides it (SPEED_SCENARIO)",
    )
    parser.add_argument(
        "--video", metavar="SOURCE",
        help="webcam index (0) or a video file, streamed at ~8 fps so dangerous moments get images (needs OpenCV)",
    )
    parser.add_argument("--replay", metavar="FRAMES_JSONL", help="replay a recorded model run instead of the demo")
    parser.add_argument(
        "--speed-kmh", type=float, default=None,
        help="replay: force a car speed (default: the backend decides; the camera doesn't know it)",
    )
    parser.add_argument("--speedup", type=float, default=1.0, help="replay: 2 = twice as fast as recorded")
    parser.add_argument("--step", type=float, default=0.5, help="replay: seconds of recording between ticks")
    args = parser.parse_args()
    if args.replay:
        run_replay(args.url, args.replay, args.speed_kmh, args.speedup, args.step, args.video)
    else:
        run_demo(args.url, args.interval, args.backend_speed, args.video)
