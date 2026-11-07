"""Jedan klip kroz pravi koordinator: start voznje -> camera_stream.py (30 s) -> kraj voznje.

Koristi tools/camera_stream.py i REST koordinatora iz ovog repoa (rivian-demo, folder iznad rivian_model/).
Rezultati prvog poredjenja (6. 11.): POREDJENJE_MODELA.md.

Pokretanje (laptop na struji; koordinator na 8000, ili sve odjednom: ..\\demo.ps1 bez kamere, pa samo korak 3):

  1) Koordinator (folder backend), fiksna brzina, bez servera:
       $env:SPEED_SCENARIO="cruise"; $env:SERVER_URL="http://127.0.0.1:8799/api/v1"
       .venv\\Scripts\\python.exe run.py --role coordinator --port 8000 --no-reload

  2) Model (folder rivian_model):
       .venv\\Scripts\\python.exe rivian_detector.py --camera 08_14
             (za klipove 05_23_* restartovati sa --camera 05_23)

  3) Klip (python iz backend venv-a, jer ima imageio-ffmpeg i websockets za camera_stream.py):
       ..\\backend\\.venv\\Scripts\\python.exe run_compare.py `
           --clip "<dataset>\\08_14_62_092916_video_inCabin.mp4" --label nas --out out_cmp

Izlaz: <out>/<label>_<klip>.json (rezime, intervali ponasanja, status modela) i <label>_<klip>_timeline.jsonl.
"""

import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # koren repoa (rivian_model/ je u njemu)
PY = REPO / "backend" / ".venv" / "Scripts" / "python.exe"


def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--seconds", type=float, default=30.0)
    a = ap.parse_args()
    base = f"http://127.0.0.1:{a.port}/api/v1"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    name = Path(a.clip).stem.replace("_video_inCabin", "")

    trip = call("POST", f"{base}/trips", {"driver_id": f"cmp-{a.label}"})
    tid = trip["trip_id"]
    cam = subprocess.Popen(
        [str(PY), str(REPO / "tools" / "camera_stream.py"), "--url", f"ws://127.0.0.1:{a.port}/api/v1/camera/ws",
         "--video", a.clip],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    t0 = time.monotonic()
    timeline, status_mid = [], None
    while (t := time.monotonic() - t0) < a.seconds:
        s = call("GET", f"{base}/trips/{tid}")
        timeline.append({"t": round(t, 2), "score": s["score"], "level": s["level"],
                         "active": s["active_behaviors"], "emergency": s["emergency_alert_sent"],
                         "response": s.get("response"),
                         "camera": (s.get("camera") or {}).get("categories")})
        if status_mid is None and t > a.seconds * 0.8:
            status_mid = call("GET", f"{base}/coordinator/status")
        time.sleep(0.25)
    cam.kill()
    cam.wait()
    summary = call("POST", f"{base}/trips/{tid}/end", {})

    # intervali po ponasanju iz timeline-a
    intervals = {}
    for rec in timeline:
        for b in rec["active"]:
            iv = intervals.setdefault(b, [])
            if iv and rec["t"] - iv[-1][1] <= 0.6:
                iv[-1][1] = rec["t"]
            else:
                iv.append([rec["t"], rec["t"]])
    first_emerg = next((r["t"] for r in timeline if r["emergency"]), None)
    result = {"clip": name, "label": a.label, "trip_id": tid, "summary": summary, "intervals": intervals,
              "first_emergency_t": first_emerg, "min_score_t": min(timeline, key=lambda r: r["score"])["t"],
              "status": status_mid}
    (out / f"{a.label}_{name}.json").write_text(json.dumps(result, indent=1, default=str))
    (out / f"{a.label}_{name}_timeline.jsonl").write_text("\n".join(json.dumps(r) for r in timeline))

    model = (status_mid or {}).get("model", {})
    print(f"{a.label} {name}: final={summary['final_score']:.0f} min={summary['min_score']:.0f} "
          f"level={summary['level']} emergency={summary['emergency_alert_sent']} (t={first_emerg})")
    for b in summary["behaviors"]:
        print(f"   {b['behavior']}: {b['occurrences']}x {b['total_seconds']:.1f}s  {intervals.get(b['behavior'])}")
    print(f"   model status: {json.dumps(model)[:400]}")


if __name__ == "__main__":
    main()
