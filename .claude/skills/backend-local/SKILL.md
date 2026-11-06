---
name: backend-local
description: Run the teammates' FastAPI backend and the drive simulator on this laptop to feed the frontend with live data. Covers venv setup on Python 3.13, starting run.py, running notebooks/safety_client.py, probing the WebSocket, and checking that the phone can reach the backend over USB or the hotspot. Use when developing or testing the mobile app or dashboard against real backend data, or when the phone can't connect.
---

# Backend + simulator for frontend work

The backend belongs to a teammate (`backend/CLAUDE.md`, contract in `docs/API.md`). We **run** it; we don't change it. Bugs or missing
fields go to PROGRESS.md → Open questions.

## One-time setup (already done on Matija's laptop)

```bash
py install 3.13                      # Python install manager, per user. 3.15 can't install fastapi[standard] (PyYAML has no wheel)
cd backend && py -3.13 -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest -q   # expect: all passed (56 on 2026-11-06)
powershell -File scripts/services.ps1 install   # once: portable Postgres 18.6 + RustFS 1.0.4 for the trip recording (~450 MB)
```

## Run (from the repo root; each long-running command in its own background shell)

```bash
cd backend && powershell -File scripts/services.ps1 start                      # Postgres :5433 + RustFS :9000 (trip recording; optional)
cd backend && .venv/Scripts/python.exe run.py                                  # 0.0.0.0:8000, auto-reload, prints the phone URL
backend/.venv/Scripts/python.exe notebooks/safety_client.py --interval 0.3     # simulated drive through every level (~35 s)
```
- Wait for `Application startup complete.` before starting clients. With the services up, the log also says
  `Recording trips to Postgres ...` and `Risky-moment clips go to ...`. Without them it warns once and keeps working;
  then `/trips/{id}/timeline` and `/events` return 503 (the app should hide its report button).
- Speed is mocked by the backend now (`TripState.speed_kmh`, `speed_source: "mock"`). The demo simulator and `tools/sim.py` still
  force their own speeds. `notebooks/safety_client.py --backend-speed` lets the mock decide, and `--video 0` streams the webcam so risky moments get clips
  (needs OpenCV: use `py -3.13`, not the backend venv). At the end it prints the worst moments with their `video_url`.
- The simulator starts **its own trip**, which ends any trip the app started (one active trip per car). Start the app's trip **after** the simulator, or let the app just watch.
- Swagger for REST: `http://localhost:8000/docs`. The WebSocket isn't listed there.
- Trips live in memory. Restarting the backend (or an auto-reload after a teammate pulls code) wipes them, and a saved `trip_id` then gives 404.

## Put the app into an exact state (`tools/sim.py`)

Deterministic alternative to the full simulator, for testing specific UI states (verified 2026-11-06 on the A54):
```bash
backend/.venv/Scripts/python.exe tools/sim.py --start --driver matija --ticks 3        # trip + clean ticks → green, 100
backend/.venv/Scripts/python.exe tools/sim.py looking_at_phone --speed 130 --ticks 12  # → caution, warning (chime), high_risk/critical (red flash + alarm)
backend/.venv/Scripts/python.exe tools/sim.py drowsy --speed 130 --ticks 2             # → emergency overlay + siren
backend/.venv/Scripts/python.exe tools/sim.py --ticks 40                               # clean driving (recovery starts after 30 s)
backend/.venv/Scripts/python.exe tools/sim.py --end                                    # trip_ended → summary
```
Run it in the background (`&`) and take phone screenshots mid-run (`android screen capture`). The flash pulses at 2 Hz, so take two shots ~0.25 s apart.

## Watch the WebSocket without the app

A small probe exists at the scratchpad path from setup, but writing a new one is trivial with the venv's `websockets`:
```python
import asyncio, json, websockets
async def main():
    async with websockets.connect("ws://127.0.0.1:8000/api/v1/ws") as ws:
        while True:
            m = json.loads(await ws.recv()); d = m["data"]
            print(m["type"], d.get("score"), d.get("level"), d.get("response"), d.get("active_behaviors"))
asyncio.run(main())
```
Run it with `backend/.venv/Scripts/python.exe -I probe.py`. Expect `trip_started` → `state`×N (+ `emergency` once) → `trip_ended`.

## Can the phone reach it?

```bash
adb reverse tcp:8000 tcp:8000      # USB path → app uses localhost:8000
adb shell "(printf 'GET /api/v1/health HTTP/1.0\r\n\r\n'; sleep 2) | toybox nc -w 5 127.0.0.1 8000"     # via USB
adb shell "(printf 'GET /api/v1/health HTTP/1.0\r\n\r\n'; sleep 2) | toybox nc -w 5 <laptop-ip> 8000"   # via hotspot
```
`{"status":"ok"}` means it's reachable. If the hotspot path fails but USB works, it's the Windows firewall (`.claude/knowledge/networking.md`).
The laptop IP is printed by `run.py`, or comes from `ipconfig` → `WiFi` IPv4.
