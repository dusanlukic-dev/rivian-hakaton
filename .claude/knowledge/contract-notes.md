# Contract notes (frontend view of `docs/API.md`)

**Source of truth: [`docs/API.md`](../../docs/API.md)**, owned by the backend and written in Serbian. Use exactly its routes, fields and types.
**Don't invent endpoints or fields.** If something is missing, that's a backend change: raise it in PROGRESS.md → Open questions
(this rule comes from the root `CLAUDE.md`). This file only adds what the frontend verified, the implications, and our proposals.

> History: early on 2026-11-06 the frontend wrote a speculative draft (`ws-protocol.md`: probabilities, levels 0–3, hello/ping/sim
> messages). The real backend landed the same day in commit `903df76` with a different design, so that draft was deleted (decisions.md D15).

## Verified on Matija's laptop, 2026-11-06

- The backend runs in `backend/.venv` (Python 3.13.17). `pytest`: 27 passed. `python run.py` binds `0.0.0.0:8000` and prints the LAN IP.
- Simulator `python notebooks/safety_client.py --interval 0.05`. The WS client received, in order: `trip_started` → 110 × `state` (with
  `emergency` right after the `state` of the tick where the score dropped below 10) → `trip_ended`.
- Phone → backend: over the hotspot `http://10.190.62.27:8000/api/v1/health` returned `{"status":"ok"}` ✅. Over USB with
  `adb reverse tcp:8000 tcp:8000` → `localhost:8000` ✅. (When testing with `toybox nc`, keep stdin open: the adb tunnel drops the
  stream on a TCP half-close. Real HTTP/WS clients are unaffected.)

## Wire-format cheat sheet (details and TS types in docs/API.md §4–6)

- WS `ws://<ip>:8000/api/v1/ws`. Server → client only: `{"type": "trip_started" | "state" | "emergency" | "trip_ended", "data": TripState | TripSummary}`.
  - `state` arrives after every camera tick (~2/s from the models, 1/s from the simulator; `--interval` goes faster) and **immediately on connect** if a trip is active.
  - **Nothing arrives while no trip is active.** There's no heartbeat, so silence isn't proof of a dead socket. During an active trip,
    > 3 s without `state` means the camera/model side stalled, so show "no data".
  - The server reads client messages but **ignores** them.
- REST `http://<ip>:8000/api/v1`: `GET /health` → `{"status":"ok"}` · `POST /trips` `{driver_id, emergency_contact?}` → 201 `TripState`
  · `POST /trips/{id}/end` → `TripSummary` (idempotent) · `GET /trips/{id}` · `GET /trips/{id}/summary` · `GET /trips?driver_id=`
  · `GET /analytics/overview` · `POST /telemetry` (**models only**, not the app).
- There's one active trip per car. A new trip ends the old one, so the WS sends `trip_ended` (old) and then `trip_started` (new).
- Trips live in memory. After a backend restart a saved `trip_id` gives 404, so go back to the start-trip screen.
- CORS is `*`, so the web dashboard may call REST directly. The Vite proxy also works.
- Types: copy docs/API.md §4 verbatim into `src/api/types.ts` in **both** apps and keep them identical. On a backend change, re-copy.

## Frontend implications

- **Show what `response` says. Never compute levels or decide on warnings yourself** (API.md §7). The per-field mapping to phone
  and dashboard effects is in `metrics-and-scoring.md`.
- Keep the socket open whenever the address is known, and reconnect with backoff (API.md §6 has a reference client). After a
  reconnect, the current `state` arrives immediately.
- API.md notes the socket drops when the app goes to the background. Our Drive-mode foreground service (`android-alerting.md`)
  exists to keep it alive.
- `emergency`: full-screen red + loud sound. Offering an SMS to the emergency contact (`Linking.openURL('sms:…')`) is proposed but not agreed.

## Proposals for the backend (not agreed yet, don't build against them)

1. ~~**Phone GPS speed → backend.**~~ **Built (2026-11-06) as an opt-in REST feature**, see "Backend storage + speed" below.
2. **Dashboard "sim panel"** posting to the existing `POST /telemetry` (behaviour toggles + speed slider), standing in for the camera
   models during demos while CV isn't ready. API.md says telemetry is "not for the app", so this needs the team's OK.
3. An optional `ack` from the phone ("I'm focused") for analytics.

## Backend storage + speed (2026-11-06, backend session; verified with real Postgres + RustFS)

All additive. Nothing the apps already use changed shape.
- `TripState` gained `speed_kmh` (the speed the tick was scored with; < 5 = standing, no penalty) and `speed_source`
  (`mock` | `phone` | `telemetry`, null before the first tick). The backend **mocks the speed** by default (a Bezier drive per trip),
  so it moves and stops on its own even when the sim panel / `tools/sim.py` send nothing. Explicit `speed_kmh` in a tick still wins.
- Report endpoints (Postgres-backed, they survive backend restarts): `GET /trips/{id}/timeline` (one `TripSample` per second) and
  `GET /trips/{id}/events?order=worst` (`RiskEvent` with `video_url` + `thumbnail_url`). Both return **`503` when recording is
  down**: hide the report button then, don't show an error. They also work for the active trip.
- `video_url` / `thumbnail_url` are **absolute URLs through the backend** (`http://<laptop-ip>:8000/api/v1/media/...`), built
  from the request's host. They work over the hotspot (port 8000 only) and over `adb reverse` (localhost). The MP4 is H.264 yuv420p with
  faststart, and the endpoint supports `Range`, so `expo-video` / `<video>` can stream and seek it.
- Phone GPS: `GET /speed` → `phone_enabled`. Only if true, `POST /speed {speed_kmh, lat?, lon?}` ~1/s (Android gives m/s, ×3.6).
  Otherwise the backend answers `409`. Off by default (`PHONE_SPEED_ENABLED`).
