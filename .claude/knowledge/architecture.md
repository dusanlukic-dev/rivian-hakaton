# Architecture

Driver-attention warnings for **hands-on assisted driving**. In-cabin camera → several small CV models → one risk score →
real-time warnings on the driver's phone and on the car's screen (a web dashboard mock).

```
 in-cabin camera
      │ frames
      ▼
 ┌────────────── CV models (CV team, notebooks/) ───────────────┐
 │ phone_use · turned_around · hands_on_wheel · drowsiness ·    │   each: score that the behaviour is happening
 │ eyes_off_road  (manual / mocked for now)                     │
 └──────────────────────────────┬───────────────────────────────┘
                                │ per-frame scores
 simulated vehicle ─────────────┤ speed_kmh, gps_speed_kmh, assist_mode, gear
                                ▼
 ┌────────────── backend/ (FastAPI, teammate) ──────────────────┐
 │ fusion: small NN or noisy-OR + persistence + speed gate      │
 │ → risk score 0..1 + level 0..3 + reasons                     │
 │ WebSocket broadcast  ws://<laptop>:8000/api/v1/ws  (10 Hz)   │
 └───────────────┬──────────────────────────────┬───────────────┘
                 │ state / alert frames          │
                 ▼                               ▼
 ┌─ frontend/mobile (Expo dev build) ─┐   ┌─ frontend/dashboard (Vite web) ─┐
 │ Drive screen: live metrics, red    │   │ mock car screen: speed, metric  │
 │ pulse, alarm, vibration, TTS, wake │   │ icons, red pulse + beeps, sim   │
 │ phone (FSI), background service    │   │ panel / scenario buttons, QR    │
 │ Settings: server IP / QR / test    │   │ code of the ws URL              │
 └────────────────────────────────────┘   └─────────────────────────────────┘
```

The laptop plays the car's computer and the phone's hotspot is the in-car network (`networking.md`).

## Ownership

| part | owner | status (see PROGRESS.md) |
|---|---|---|
| `notebooks/` CV models | CV team | manual and slow, so mock everything |
| `backend/` FastAPI fusion + WS | teammate `dusanlukic-dev` | in development, not pushed as of 2026-11-06 |
| `frontend/mobile` | us (Matija + agents) | scaffolded, dev build being set up |
| `frontend/dashboard` | us | starter copied, not adapted yet |
| contract | shared | `ws-protocol.md` DRAFT v0, frontend proposal |

## Frontend internals (planned, the same shape in both apps)

```
src/protocol/   types.ts (internal model) · normalize.ts (backend JSON → internal model, the ONLY place that knows the wire format)
                fallback.ts (client-side level when `risk` is missing)
src/connection/ useCarSocket(): WebSocket with never-give-up reconnect, 3 s staleness watchdog, hello/ping
src/alerts/     alert engine: level transitions + hysteresis → effects (sound, vibration, flash, notification, TTS)
src/settings/   server URL store (AsyncStorage on mobile / localStorage on web)
```

- A **mock server** (planned: `tools/mock-server/`, Node + `ws`, listening on `:8000/api/v1/ws`) emits `state` frames for the
  scenarios in `metrics-and-scoring.md`, so the frontend never waits on the backend or the CV team.
- The **adapter rule**: when the backend's real format arrives, only `normalize.ts` should need to change.
