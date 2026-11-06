"""Bridge between the camera models (YOLO / MediaPipe / OpenCV) and the backend.

Standard library only. Keep it next to the notebooks and:

    from safety_client import SafetyClient

    client = SafetyClient()  # backend running on the same laptop
    # inside the camera loop - calling it every frame is fine, it throttles itself (~2/s):
    client.send_frame(record, speed_kmh=60)  # record = the dict you write to frames.jsonl

The backend maps the record's active categories to its labels (phone_use -> looking_at_phone...)
and forwards risk / alert / categories to the app. `perception` (raw detector output) is dropped
here; the app doesn't need it. If you only have labels, use `client.send({"looking_at_phone"}, 60)`
with the names in BEHAVIORS.

Run this file directly to drive the backend without any models (useful for the app team):

    python safety_client.py                          # simulated drive through every level
    python safety_client.py --interval 0.3           # faster than real time
    python safety_client.py --replay frames.jsonl    # replay a recorded model run
    python safety_client.py --replay frames.jsonl --speedup 2 --speed-kmh 90
"""

import argparse
import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self._last_sent = float("-inf")

    def send_frame(
        self, record: dict, speed_kmh: float, timestamp: datetime | None = None
    ) -> dict | None:
        """Report one model record (a line of frames.jsonl), unchanged.

        Returns the new trip state, or None if the call was throttled, no trip is active
        yet, or the backend is unreachable (so a hiccup never kills the camera loop).
        """
        frame = {key: value for key, value in record.items() if key != "perception"}
        return self._send_tick({"frame": frame}, speed_kmh, timestamp)

    def send(
        self, behaviors: Iterable[str], speed_kmh: float, timestamp: datetime | None = None
    ) -> dict | None:
        """Report backend labels directly (see BEHAVIORS). Same return value as send_frame."""
        behaviors = set(behaviors)
        unknown = behaviors - BEHAVIORS
        if unknown:
            raise ValueError(f"Unknown behaviors {sorted(unknown)}; use one of {sorted(BEHAVIORS)}")
        return self._send_tick({"behaviors": sorted(behaviors)}, speed_kmh, timestamp)

    def start_trip(self, driver_id: str, emergency_contact: dict | None = None) -> dict:
        return self._post("/trips", {"driver_id": driver_id, "emergency_contact": emergency_contact})

    def end_trip(self, trip_id: str) -> dict:
        return self._post(f"/trips/{trip_id}/end")

    def _send_tick(self, payload: dict, speed_kmh: float, timestamp: datetime | None) -> dict | None:
        now = time.monotonic()
        if now - self._last_sent < self.min_interval_s:
            return None
        self._last_sent = now

        body = {
            # Local time with offset - the backend uses the hour for night penalties.
            "timestamp": (timestamp or datetime.now().astimezone()).isoformat(),
            "speed_kmh": speed_kmh,
            **payload,
        }
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


def _print_state(speed: float, seen: str, state: dict) -> None:
    r = state["response"]
    camera = state.get("camera") or {}
    model = f"  model={camera.get('alert')}/{camera.get('risk')}" if camera else ""
    print(
        f"{speed:>4} km/h  {seen or '-':<28} score={state['score']:>5}  "
        f"{state['level']:<10} light={r['dashboard_light']:<12} "
        f"vibrate={r['vibrate_seat']!s:<5} sound={r['sound']}{model}"
    )


def _print_summary(summary: dict) -> None:
    print(f"\nFinal score {summary['final_score']} (avg {summary['average_score']}, min {summary['min_score']})")
    for b in summary["behaviors"]:
        print(f"  {b['behavior']}: {b['occurrences']}x, {b['total_seconds']} s - {b['tip']}")


def run_demo(base_url: str, interval_s: float) -> None:
    client = SafetyClient(base_url, min_interval_s=0)
    trip = client.start_trip("demo-driver", {"name": "Demo Contact", "phone": "+381600000000"})
    print(f"Started trip {trip['trip_id']}")

    ts = datetime.now().astimezone()
    for seconds, speed, behaviors in DEMO_DRIVE:
        for _ in range(seconds):
            ts += timedelta(seconds=1)  # simulated clock, so --interval can run faster than real time
            state = client.send(behaviors, speed, timestamp=ts)
            if state is None:
                raise SystemExit("Backend unreachable or trip ended - is the server running?")
            _print_state(speed, ",".join(behaviors), state)
            time.sleep(interval_s)

    _print_summary(client.end_trip(trip["trip_id"]))


def run_replay(base_url: str, path: str, speed_kmh: float, speedup: float, step_s: float) -> None:
    """Replay a recorded frames.jsonl as if the camera were live, paced by each record's `t`."""
    client = SafetyClient(base_url, min_interval_s=0)  # throttled below on the recording's clock
    trip = client.start_trip("replay-driver", {"name": "Demo Contact", "phone": "+381600000000"})
    print(f"Started trip {trip['trip_id']}, replaying {path}")

    start = datetime.now().astimezone()
    last_t: float | None = None
    with open(path, encoding="utf-8") as lines:
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
            _print_state(speed_kmh, ",".join(active), state)

    _print_summary(client.end_trip(trip["trip_id"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate or replay a drive against the backend.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--interval", type=float, default=1.0, help="demo: real seconds between ticks")
    parser.add_argument("--replay", metavar="FRAMES_JSONL", help="replay a recorded model run instead of the demo")
    parser.add_argument("--speed-kmh", type=float, default=60.0, help="replay: car speed (the camera doesn't know it)")
    parser.add_argument("--speedup", type=float, default=1.0, help="replay: 2 = twice as fast as recorded")
    parser.add_argument("--step", type=float, default=0.5, help="replay: seconds of recording between ticks")
    args = parser.parse_args()
    if args.replay:
        run_replay(args.url, args.replay, args.speed_kmh, args.speedup, args.step)
    else:
        run_demo(args.url, args.interval)
