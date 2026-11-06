"""Bridge between the camera models (YOLO / MediaPipe / OpenCV) and the backend.

Standard library only. Keep it next to the notebooks and:

    from safety_client import SafetyClient

    client = SafetyClient()  # backend running on the same laptop
    # inside the camera loop - calling it every frame is fine, it throttles itself:
    client.send(behaviors={"looking_at_phone", "hands_off_wheel"}, speed_kmh=60)

Valid behaviors are listed in BEHAVIORS. Map your detections to them here, on the model
side (e.g. MediaPipe head pose pointing down + YOLO "cell phone" -> "looking_at_phone");
the backend only gets labels, never images.

Run this file directly to simulate a whole drive without any models (useful for the app team):

    python safety_client.py
    python safety_client.py --interval 0.3     # faster than real time
"""

import argparse
import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from datetime import datetime, timedelta

BEHAVIORS = frozenset({
    "looking_at_phone",  # gleda u telefon
    "looking_behind",    # gleda iza sebe
    "turning_around",    # okreće se (telom)
    "hands_off_wheel",   # ruke van volana
    "drowsy",            # pospan
})


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

    def send(
        self, behaviors: Iterable[str], speed_kmh: float, timestamp: datetime | None = None
    ) -> dict | None:
        """Report what the camera sees right now.

        Returns the new trip state, or None if the call was throttled, no trip is active
        yet, or the backend is unreachable (so a hiccup never kills the camera loop).
        """
        behaviors = set(behaviors)
        unknown = behaviors - BEHAVIORS
        if unknown:
            raise ValueError(f"Unknown behaviors {sorted(unknown)}; use one of {sorted(BEHAVIORS)}")

        now = time.monotonic()
        if now - self._last_sent < self.min_interval_s:
            return None
        self._last_sent = now

        body = {
            # Local time with offset - the backend uses the hour for night penalties.
            "timestamp": (timestamp or datetime.now().astimezone()).isoformat(),
            "speed_kmh": speed_kmh,
            "behaviors": sorted(behaviors),
        }
        try:
            return self._post("/telemetry", body)
        except urllib.error.HTTPError as e:
            if e.code == 409:  # no active trip - the app hasn't started one yet
                return None
            raise
        except urllib.error.URLError:
            return None

    def start_trip(self, driver_id: str, emergency_contact: dict | None = None) -> dict:
        return self._post("/trips", {"driver_id": driver_id, "emergency_contact": emergency_contact})

    def end_trip(self, trip_id: str) -> dict:
        return self._post(f"/trips/{trip_id}/end")

    def _post(self, path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body).encode() if body is not None else b"",
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
            r = state["response"]
            print(
                f"{speed:>4} km/h  {','.join(behaviors) or '-':<28} score={state['score']:>5}  "
                f"{state['level']:<10} light={r['dashboard_light']:<12} "
                f"vibrate={r['vibrate_seat']!s:<5} sound={r['sound']}"
            )
            time.sleep(interval_s)

    summary = client.end_trip(trip["trip_id"])
    print(f"\nFinal score {summary['final_score']} (avg {summary['average_score']}, min {summary['min_score']})")
    for b in summary["behaviors"]:
        print(f"  {b['behavior']}: {b['occurrences']}x, {b['total_seconds']} s - {b['tip']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate a drive against the backend.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--interval", type=float, default=1.0, help="real seconds between ticks")
    args = parser.parse_args()
    run_demo(args.url, args.interval)
