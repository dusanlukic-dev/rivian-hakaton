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
of sight; a 30 s clip takes a few seconds), then **Send** streams them.

## Before a test or the demo

1. Backend: `python run.py` in `backend/`.
2. Model worker: `python ..\model\worker.py`, or `--fake` for scripted detections. Without a worker the frames only
   fill the video cache (images of dangerous moments) and the score doesn't move.
3. `SPEED_SCENARIO=cruise` in `backend/.env`. The default random mock drive can be standing still (below 5 km/h there
   is no danger and no alarm) right while the clip plays.
4. Start the trip from the phone first. If no trip is active, Send starts one as driver `video-sim`, which belongs to
   no account (the phone won't find it in its history).
5. This tab may go to the background (e.g. the dashboard in front): sending runs in a Web Worker and keeps its pace.
   Only the preparation needs the tab visible.

Check while sending: `curl http://127.0.0.1:8000/api/v1/coordinator/status` shows `camera.fps` around 10 and
`model.frames_sent` rising.

## How it works

- **Choosing a file:** the clip plays once at 4× (slower if the browser can't keep up) and a JPEG is grabbed every
  0.1 s of video with `requestVideoFrameCallback`: 80 % quality, at most 1280 px wide. A 30 s clip gives 300 frames,
  some tens of MB in memory.
- **Send:** `GET /api/v1/coordinator/status`, and only if there is no `trip_id`, `POST /api/v1/trips` with
  `{"driver_id": "video-sim"}` (that call ends a trip in progress). Then a Web Worker opens `WS /api/v1/camera/ws` and
  sends frame *i* at *i* × 100 ms, one binary message per JPEG, never faster than real time. A late frame is skipped,
  not queued, like the backend's model, which only takes the newest frame.
- **Why real time:** the backend measures time by frame arrival (the model's clock, how long a behaviour lasts, the
  2 s sections). A clip sent faster would look like a shorter drive.
- **Why 10 fps:** the backend's video cache keeps at most 10 frames per second.
- **End of the clip:** sending stops and the socket closes; the trip goes on. Send again starts the same clip over.

## Limits

- Up to 2 minutes, since every frame is kept in memory. MP4 (H.264) or WebM; HEVC `.mov` from an iPhone usually won't
  decode in Chrome, so export it as MP4 (H.264).
- After the clip the backend gets no more detections, so the phone and the dashboard stay on the last state until the
  next clip or the end of the trip.
- If the phone ends the trip mid-clip, the backend drops the rest of the frames without saying so.
- Don't run `tools/camera_stream.py` at the same time: both streams would mix in the same trip.

## Tests

```bash
npm test         # Vitest in Node: frame math, real-time schedule, sender, backend client, page controller
npm run build
npm run lint
```

Design and plan: [docs/2026-11-07-video-sim-design.md](docs/2026-11-07-video-sim-design.md),
[docs/2026-11-07-video-sim-plan.md](docs/2026-11-07-video-sim-plan.md).
