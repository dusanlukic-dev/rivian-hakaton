# Video sim

Plays a recorded in-cabin clip as if it were the car's camera. The frames go to the backend's camera socket
(`WS /api/v1/camera/ws`) in real time, the same path `tools/camera_stream.py` uses, so the backend can't tell the
difference: model worker → risk engine → score → phone and dashboard, as with a live camera. Nothing from the backend
is shown here: watch the phone or the dashboard.

## Run

```bash
cp .env.example .env     # VITE_API_URL = the backend, default http://localhost:8000
npm install
npm run dev              # http://localhost:5174 (the dashboard is on 5173)
```

Drop a clip (up to 2 minutes, MP4/H.264 or WebM) on the page. It prepares the frames (the clip plays once, fast and out
of sight; a 30 s clip takes a few seconds). Then either:

- **start a trip on the phone**: the page sees the new trip and plays the clip into it from the start, or
- press **Send**.

**One clip = one trip, so the score starts at 100 with every clip.** The coordinator starts every trip fresh (score,
risk engine, model memory), and the page never sends a second clip into a trip that already had frames.

## Before a test or the demo

1. The car without a camera: `.\demo.ps1 -Camera 05_23` from the repo root (no `-Video`, `-Webcam` or `-PoVoznji`:
   the coordinator takes one camera, and this page is it). Or by hand: backend `python run.py` in `backend/` and the
   model `rivian_model\rivian_detector.py --camera 05_23` (README there). Without the model the frames only fill the
   video cache (images of dangerous moments) and the score doesn't move.
2. Clips from the camera series the model was started with (`05_23_*` for `--camera 05_23`): it sets the driver zone.
3. Speed scenario `cruise` (the `demo.ps1` default, or `SPEED_SCENARIO=cruise`). A random mock drive can be standing
   still (below 5 km/h there is no danger and no alarm) right while the clip plays.
4. Start trips from the phone: they belong to the account (History, reports). Send starts a trip as driver
   `video-sim` whenever the trip in progress already had frames, and that one belongs to no account.
5. This tab may go to the background (e.g. the dashboard in front): sending runs in a Web Worker and keeps its pace,
   and trip starts arrive over a WebSocket. Only the preparation needs the tab visible.

Check while sending: `curl http://127.0.0.1:8000/api/v1/coordinator/status` shows `camera.fps` around 10 and
`model.frames_sent` rising.

## How it works

- **Choosing a file:** the clip plays once at 4× (slower if the browser can't keep up) and a JPEG is grabbed every
  0.1 s of video with `requestVideoFrameCallback`: 80 % quality, at most 1280 px wide. A 30 s clip gives 300 frames,
  some tens of MB in memory.
- **Trips:** the page listens to `WS /api/v1/ws` (the phone's live socket) for three things only: `trip_started`,
  `trip_ended`, and `state` with a `speed_source` (null before a trip's first tick, so a trip with one has been scored
  already). A trip it sent a clip into, or saw scored, is used.
  - `trip_started` from someone else (the phone) while a clip is loaded: a clip still playing stops, and the clip
    starts over in the new trip.
  - **Send:** `GET /api/v1/coordinator/status`. An unused `trip_id` gets the clip; otherwise `POST /api/v1/trips` with
    `{"driver_id": "video-sim"}` starts a new trip (the coordinator ends the one in progress).
  - `trip_ended` of the trip it sends into: sending stops.
- **Sending:** a Web Worker opens `WS /api/v1/camera/ws` and sends frame *i* at *i* × 100 ms, one binary message per
  JPEG, never faster than real time. A late frame is skipped, not queued, like the backend's model, which only takes
  the newest frame. A socket refused before it opens is retried (6 tries, 400 ms apart): right after a send stops, the
  coordinator may still count the old camera, and it takes only one.
- **Why real time:** the backend measures time by frame arrival (the model's clock, how long a behaviour lasts, the
  2 s sections). A clip sent faster would look like a shorter drive.
- **Why 10 fps:** the backend's video cache keeps at most 10 frames per second.
- **End of the clip:** sending stops and the socket closes; the trip goes on. Send again plays the clip in a new trip.

## Limits

- Up to 2 minutes, since every frame is kept in memory. MP4 (H.264) or WebM; HEVC `.mov` from an iPhone usually won't
  decode in Chrome, so export it as MP4 (H.264).
- After the clip the backend gets no more detections, so the phone and the dashboard stay on the last state ("No data
  from the camera") until the next clip or the end of the trip.
- One camera at a time: with `tools/camera_stream.py` or `rivian_model/klip_po_voznji.py` running, the coordinator
  refuses this page's socket ("Another camera may be streaming"), or the other one takes the slot on a new trip.

## Tests

```bash
npm test         # Vitest in Node: frame math, real-time schedule, sender, backend client, trip events, page controller
npm run build
npm run lint
```

Design and plan: [docs/2026-11-07-video-sim-design.md](docs/2026-11-07-video-sim-design.md),
[docs/2026-11-07-video-sim-plan.md](docs/2026-11-07-video-sim-plan.md).
