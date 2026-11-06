"""Drive the backend into a specific state for UI testing: stands in for the camera models.

Uses notebooks/safety_client.py (stdlib only). Run with the backend venv from the repo root:

  backend/.venv/Scripts/python.exe tools/sim.py --start                       # start a trip (driver "sim-driver")
  backend/.venv/Scripts/python.exe tools/sim.py looking_at_phone --ticks 6    # 6 ticks (1/s) of phone use at 80 km/h
  backend/.venv/Scripts/python.exe tools/sim.py drowsy --speed 130 --ticks 4  # push towards emergency
  backend/.venv/Scripts/python.exe tools/sim.py --ticks 40                    # clean driving (recovery after 30 s)
  backend/.venv/Scripts/python.exe tools/sim.py --end                         # end the active trip

Behaviours: looking_at_phone, eyes_off_road, looking_behind, turning_around, hands_off_wheel, drowsy.
Ticks use real time (the backend scores by timestamp), so --interval below 1 s makes penalties smaller.
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))
from safety_client import BEHAVIORS, SafetyClient  # noqa: E402


def active_trip(base: str) -> dict | None:
    with urllib.request.urlopen(f"{base}/trips", timeout=3) as r:
        trips = json.load(r)
    return next((t for t in reversed(trips) if t["status"] == "active"), None)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("behaviors", nargs="*", help=f"any of {sorted(BEHAVIORS)}")
    p.add_argument("--url", default="http://127.0.0.1:8000/api/v1")
    p.add_argument("--speed", type=float, default=80)
    p.add_argument("--ticks", type=int, default=0)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--start", action="store_true", help="start a new trip first")
    p.add_argument("--driver", default="sim-driver")
    p.add_argument("--end", action="store_true", help="end the active trip at the end")
    a = p.parse_args()

    client = SafetyClient(a.url, min_interval_s=0)
    if a.start:
        trip = client.start_trip(a.driver, {"name": "Sim Contact", "phone": "+381600000000"})
        print(f"started trip {trip['trip_id']} for {a.driver}")

    for _ in range(a.ticks):
        state = client.send(a.behaviors, a.speed)
        if state is None:
            sys.exit("no active trip (start one in the app or with --start)")
        r = state["response"]
        print(f"score={state['score']:>5}  {state['level']:<10} light={r['dashboard_light']:<12} "
              f"vibrate={r['vibrate_seat']!s:<5} sound={r['sound']:<4} active={state['active_behaviors']}")
        time.sleep(a.interval)

    if a.end:
        trip = active_trip(a.url)
        if trip:
            s = client.end_trip(trip["trip_id"])
            print(f"ended {s['trip_id']}: final {s['final_score']} (avg {s['average_score']}, min {s['min_score']})")
        else:
            print("no active trip to end")


if __name__ == "__main__":
    main()
