---
name: backend-local
description: Run the backend (coordinator + server) with Postgres and RustFS in Docker, then feed it like the car would - the camera stream plus the model worker (fake or real), or the drive simulator - to give the frontend live data, sections and drive reports. Covers venv setup on Python 3.13, docker compose, run.py roles, tools/camera_stream.py, model/worker.py, notebooks/safety_client.py, tools/sim.py, the coordinator status endpoint, probing the WebSocket, restarting the server safely on Windows, and checking that the phone can reach it. Use when developing or testing the mobile app or dashboard against real backend data, or when the phone can't connect.
---

# Backend + camera + model (or simulator) for frontend work

The backend has two parts (`docs/ARCHITECTURE.md`): the **coordinator** (live: WS, camera, model link, score, 2 s sections) and
the **server** (accounts, storage, report). `python run.py` runs both in one process on :8000. Since 2026-11-06 evening we work on
the backend too (user's request); rules in `backend/CLAUDE.md`, contract in `docs/API.md`.

## One-time setup (done on Matija's laptop)

```bash
py install 3.13                      # 3.15 can't install fastapi[standard] (PyYAML has no wheel)
cd backend && py -3.13 -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest -q   # expect: all passed (81 on 2026-11-06)
```
Storage: **Docker Desktop is installed on this laptop now**, so use `docker compose` (below). The portable alternative
(`backend/scripts/services.ps1 install` + `start`, no Docker) is what the backend teammate's laptop uses.

## Run (from the repo root)

```bash
cd backend && docker compose up -d                                   # Postgres :5433 + RustFS :9000 (containers backend-postgres-1 / -rustfs-1)
cd backend && .venv/Scripts/python.exe run.py                       # coordinator + server, 0.0.0.0:8000, auto-reload, prints the phone URL
backend/.venv/Scripts/python.exe tools/camera_stream.py             # camera stand-in: test pattern 10 fps (--video clip.mp4, --webcam "name")
backend/.venv/Scripts/python.exe model/worker.py --fake             # model worker without CV packages: scripted 60 s loop of detections
curl -s http://127.0.0.1:8000/api/v1/coordinator/status             # camera fps, model connected/latency, video cache, server delivery
```
- Long-running things go in their own background shell. To keep the **backend alive after the agent session**, start it in
  its own window: `Start-Process <backend>\.venv\Scripts\python.exe -ArgumentList run.py -WorkingDirectory <backend> -WindowStyle Minimized`.
- **Restarting the backend on Windows:** kill the whole tree. Killing only the reloader leaves its `multiprocessing-fork` worker
  alive, still bound to :8000 (Windows lets two sockets share the port), so **old code keeps answering**. Check with
  `Get-NetTCPConnection -LocalPort 8000` and `Get-CimInstance Win32_Process -Filter "Name='python.exe'"`; the version is in
  `/openapi.json` (`info.version`, 0.4.0 = coordinator/server split).
- Startup log: `Server stores trips in Postgres ...`, `Dangerous-moment images go to ...`, `Risk engine (CV team's model) uses ...`,
  `Video cache on disk: ...`, `Coordinator ready: sections of 2.0 s, server in-process`. Without Postgres it warns once and the live
  path keeps working; history/report return 503 (the app hides the chart).
- With camera + fake worker running, **any trip started from the phone gets fake detections** (phone at 14–20 s of every minute,
  look-away 28–31 s, microsleep 38–41 s, hands off 48–52 s). Stop them (or don't start them) when testing something else.
- Speed is mocked by the coordinator (`SPEED_SCENARIO`, random per trip; `cruise` never stops, good for a stage demo).
- One active trip per car: a new trip (simulator or app) ends the old one.
- Swagger for REST: `http://localhost:8000/docs`. WebSockets aren't listed there.

## Simulator instead of camera + model

```bash
backend/.venv/Scripts/python.exe notebooks/safety_client.py --interval 0.3     # whole drive through every level (~35 s), ends the trip
```
It starts **its own trip** and sends labels only (no `camera`, no section images). `--video 0` streams the webcam (needs OpenCV,
`py -3.13`, not the backend venv) so dangerous sections get images; at the end it prints the worst moments with their `image_url`.
Don't run it while the model worker is connected: both would score the same trip.

### Put the app into an exact state (`tools/sim.py`)
```bash
backend/.venv/Scripts/python.exe tools/sim.py --start --driver matija --ticks 3        # trip + clean ticks → green, 100
backend/.venv/Scripts/python.exe tools/sim.py looking_at_phone --speed 130 --ticks 12  # → caution, warning (chime), high_risk/critical (red flash + alarm)
backend/.venv/Scripts/python.exe tools/sim.py drowsy --speed 130 --ticks 2             # → emergency overlay + siren
backend/.venv/Scripts/python.exe tools/sim.py --ticks 40                               # clean driving (recovery starts after 30 s)
backend/.venv/Scripts/python.exe tools/sim.py --end                                    # trip_ended → summary
```
Take phone screenshots mid-run. The flash pulses at 2 Hz, so take two shots ~0.25 s apart.

## Check the report of a trip

```bash
curl -s http://127.0.0.1:8000/api/v1/trips/<id>/report | python -m json.tool | less    # sections (2 s) + moments with image_url
curl -s -X POST http://127.0.0.1:8000/api/v1/trips -H "Content-Type: application/json" -d '{"driver_id":"me"}'   # start a trip by hand
curl -s -X POST http://127.0.0.1:8000/api/v1/trips/<id>/end                                                       # end it
```
A fake-worker trip of ~2 min gives ~60 sections and ~8 moments with images (verified 2026-11-06 with Postgres + RustFS in Docker).

## Watch the WebSocket without the app

```python
import asyncio, json, websockets
async def main():
    async with websockets.connect("ws://127.0.0.1:8000/api/v1/ws") as ws:
        while True:
            m = json.loads(await ws.recv()); d = m["data"]
            print(m["type"], d.get("score"), d.get("level"), d.get("danger"), d.get("behaviors") or d.get("active_behaviors"))
asyncio.run(main())
```
Run it with `backend/.venv/Scripts/python.exe -I probe.py`. Expect `trip_started` → `state` ~2/s (+ `emergency` once) and
`section` every 2 s → `trip_ended`.

## Can the phone reach it?

```bash
adb reverse tcp:8000 tcp:8000      # USB path → app uses localhost:8000 (re-apply after every USB reconnect)
adb shell "(printf 'GET /api/v1/health HTTP/1.0\r\n\r\n'; sleep 2) | toybox nc -w 5 127.0.0.1 8000"     # via USB
adb shell "(printf 'GET /api/v1/health HTTP/1.0\r\n\r\n'; sleep 2) | toybox nc -w 5 <laptop-ip> 8000"   # via hotspot
```
`{"status":"ok"}` means it's reachable. If the hotspot path fails but USB works, it's the Windows firewall (`.claude/knowledge/networking.md`).
The laptop IP is printed by `run.py`, or comes from `ipconfig` → `WiFi` IPv4.
