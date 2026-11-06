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

## Types re-copied (2026-11-06, after the camera + storage changes)

- Both apps' `src/api/types.ts` = docs/API.md §4 as of `7d6e66b` (`eyes_off_road`, `CameraView`, `speed_kmh` / `speed_source`,
  report and speed types). `eyes_off_road` has a tile in both apps. Nothing *shows* `camera`, `speed_kmh` or the report yet.
- `camera.categories` keys are the **model's** names (`phone_use`, `eyes_off_road`, `hands_off_wheel`, `eating_drinking`, `drowsiness`,
  `eyes_closed`), not `Behavior`. `eating_drinking` arrives there but is never scored.
- Hand-built `TripState` objects (mobile `fakeState` in `state/live.ts`) need the new required fields: `camera`, `speed_kmh`, `speed_source`.

## Backend storage + speed (2026-11-06, backend session; verified with real Postgres + RustFS)

> **Superseded in part** by the coordinator/server split below: `/timeline`, `/events`, `TripSample`, `RiskEvent` and clips are gone.

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

## Accounts + trip report (2026-11-06, backend session; verified on real Postgres)

> The report's `samples`/`events` became `sections`/`moments` (see below). Accounts are unchanged.

Additive, except `TripCreate.driver_id` became optional. Clients that send it keep working unchanged.
- **The app requires login (2026-11-07, D36);** the backend still doesn't. `POST /auth/register` or `/auth/login` returns `AuthOut {token, token_type, expires_at, user}`. Send
  `Authorization: Bearer <token>` on REST calls. The token is opaque (not a JWT) and lasts 30 days. The dashboard template's
  AuthProvider still works, it just can't decode claims. On any `401`, drop the token and show login.
- With a token, `POST /trips` may send `{}`. The trip gets `driver_id` = username and the account's saved emergency contact.
  The trip is then **private**: the summary, report and history work only with that token, and everyone else gets `404`.
  Trips started without a token behave as before.
- `GET /trips` with a token = my trips, from Postgres, so they survive backend restarts. Without a token = trips without login,
  optionally filtered by `driver_id`. `GET /trips/{id}/summary` also survives restarts now.
- Implemented 2026-11-07: `state/auth.ts` (token + user, AsyncStorage `auth.v1`), `api/client.ts` adds `Authorization` to every call and
  logs out on a 401, `app/login.tsx` (log in / create account + the car-computer address), root layout `Stack.Protected` guards with
  explicit `redirectTo` (without them expo-router fell back to the QR scanner). The old local profile (`state/profile.ts`) is gone.
- Profile ↔ account mapping (was the local profile): `driverId` = `user.username`, `name` = `display_name`, contact = `emergency_contact`. Edit with
  `PATCH /auth/me`.
- **`GET /trips/{id}/report`** is the report screen in one call: `trip` (TripSummary) + `user` + `samples` (raw per-second rows:
  `t`, `score`, `speed_kmh`, `behaviors`, model `categories`...) + `events` (with `thumbnail_url` / `video_url`). Charts are the app's
  job, computed from `samples`. `503` = recording down → hide the report.

## Coordinator / server split (2026-11-06 evening, our session; verified with Postgres + RustFS in Docker)

The backend is now two parts behind the same `http://<ip>:8000/api/v1` (`docs/ARCHITECTURE.md`): the **coordinator** answers the
live routes (WS, `POST /trips`, `/end`, `GET /trips/{id}`, `/speed`, `/telemetry`, `/video/frames`) and the **server** the stored
ones (`/auth/*`, `GET /trips`, `/summary`, `/report`, `/sections`, `/media`, `/analytics`). API.md §5 tags each route [K] / [S].
What changed for the apps (both `src/api/types.ts` re-copied from §4 the same day):
- **New WS message `section`** every 2 s of driving (and one when the trip ends): `TripSection` = what was seen in those 2 s
  (`behaviors` in seconds, model `categories`, `alert`, `risk_max`), `score_start/end/min`, `danger` (`none` | `dangerous` |
  `critical`), speed, car response. `image_url` is always null live; the report has it. Unknown message types must be ignored.
- **`state` from the model path is throttled to ~2/s** (plus at once on any change of level, response, behaviours or model alert),
  because the model scores 5–10 frames a second and the phone vibrates/beeps per message. `/telemetry` (simulator) is unchanged.
- **`POST /trips` no longer fails (503) when the server is unreachable** and the phone sends a token (2026-11-06, D34): the trip
  starts; for a token the coordinator never checked, `driver_id` is the body's or `"unverified-login"` until the server puts the
  trip on the account. The app should show the name from its own profile, not `driver_id`. `/telemetry` is debug-only now.
- **`TripReport` = `{trip, user, section_s, sections, moments}`.** `samples`, `window_s`, `events`, `TripSample`, `RiskEvent`,
  `TripTimeline`, `/timeline`, `/events` and the MP4 clips are gone. `GET /trips/{id}/sections?after_seq=N` returns new sections.
- `DangerMoment` = back-to-back dangerous sections merged by the server: node at (`peak_t`, `peak_score`), `image_url` of the
  riskiest frame, `behaviors` (seconds), `categories`, `score_drop`. Draw an image box above `critical` ones (the user's "ultra
  dangerous" nodes). Both apps implement exactly that (`components/report.tsx`, `CarScreen/DriveReport.tsx`).
- History/summary/report come only from Postgres now: `503` while it's down (the coordinator keeps sections and delivers them
  later). The summary of a running trip lags at most one section (~2 s). `POST /trips/{id}/end` waits up to 3 s for delivery, so
  the report opened right after "End" is complete.
- `POST /trips` with a token is `503` if the server can't be asked about the token (the coordinator checks logins via `GET /auth/me`).
- `GET /coordinator/status` (diagnostics, not part of the app contract): camera fps, model worker, video cache, server delivery.

## Live score + summary semantics (2026-11-07, D35)

- `TripState.score` is a **live reading** (falls while something risky happens, back at 100 a few seconds later), not a balance.
  Nothing changes in the types; the UI already showed it as the big number.
- `TripSummary.level` is now the level of **`average_score`** (moving time only); `final_score` is the live score at the end (~100 once
  parked). Both apps headline `average_score` + `level` (history badges, summary hero, dashboard summary card).
- Standing still (< 5 km/h): `response` is green/silent with "Standing still - no warnings." whatever the driver does.
- The dashboard's report for a **logged-in** trip is 404 (private to the account): the chart just hides there; the phone shows it.
- After a backend restart mid-trip the app now asks `GET /trips/{id}` on reconnect and drops the trip on 404; "End" on such a trip
  opens its stored summary instead of an error.
