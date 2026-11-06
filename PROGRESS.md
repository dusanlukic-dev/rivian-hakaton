# PROGRESS

> Live status board for humans and agents. **Read it first, update it last** (`.claude/rules/progress.md`).
> Keep it short and link to files. Details belong in `.claude/knowledge/`. Domain rules: root `CLAUDE.md`. Contract: `docs/API.md`.
> Last updated: 2026-11-06, architecture check against the user's definition (one camera path, debug feed, offline login, setup_models fixed) (Claude, for Matija).

## Snapshot

| area | state |
|---|---|
| Backend (FastAPI) | ✅ **two parts** (`docs/ARCHITECTURE.md`), one process on :8000 (`python run.py`; split with `--role` + `SERVER_URL`). **Coordinator** (`app/coordinator`): phone WS, camera stream (`WS /camera/ws`, `POST /video/frames`), **model worker link** (`WS /model/ws`), the CV team's `RiskEngine` (extracted, identical to the original: test), score + car response, **5 min video cache** (diskcache), a **section summary every 2 s** (score, what was seen, `danger`, image of the riskiest frame when dangerous) to the phone (WS `section`) and to the server (outbox, retries while it's down), plus the camera model's trip report (`app/services/model_report.py`). **Checked against the user's definition (session 6):** the car = camera + model + coordinator, the server is outside; `/telemetry` frame records are a debug feed (409 while a model worker is connected), a phone login never blocks the car (offline: stale token cache, or the token rides along as `TripMeta.owner_token`). **Server** (`app/server`): accounts, Postgres (`trips`, `trip_sections`) + RustFS images, history, **`GET /trips/{id}/report`** = summary + user + sections + **moments** (merged dangerous sections with an image) + `model`. 92 tests. Speed is mocked by the coordinator (phone GPS opt-in) |
| Camera + model | ✅ `tools/camera_stream.py` (test pattern / clip / webcam → coordinator) + `model/worker.py` (own venv; CV detectors imported unchanged; `--fake` = scripted detections, verified end to end with Postgres + RustFS). Real-model mode written, **not run here** (no YOLO model or dataset on this laptop; the face/hand `.task` files are in `notebooks/models/` now): `model/README.md`. `notebooks/setup_models.bat`/`.sh` fixed (conflict resolved, yolo11s/640) |
| Simulators | ✅ `notebooks/safety_client.py` (full demo drive, `--replay frames.jsonl`, `--video 0` streams the webcam so dangerous moments get images, `--backend-speed`) + `tools/sim.py` (exact states, see skill `backend-local`) |
| CV models | `notebooks/risk_pipeline.py` + `risk_config.json` (ttcpavle). **Fixed (session 3):** it was watching the passenger (driver is on the RIGHT of this camera); face now searched in `head_roi`, look-down vs eyes-closed retuned, yolo11s/640, `--show` panel with every variable, checked on all 56 clips. Book: `.claude/knowledge/cv-pipeline.md`. **Session 4:** `--mode dev` (video + reduced metrics panel, `dev_overlay.py`) and `--mode prod` (headless, streams frames ~2/s + video to the backend from background threads; `--start-trip` for runs without the phone). Per-frame math only; trip summary/episodes moved to the backend. Run instructions: `notebooks/pokretanje.txt`. **One real path:** camera → coordinator → `model/worker.py`; their `--mode prod` → `/telemetry` is **debug only** (D34) |
| Contract | ✅ `docs/API.md` (source of truth; §5 tags each route [K] coordinator / [S] server). New: WS `section`, report `sections` + `moments` (+ `model`). Internal contracts: `docs/ARCHITECTURE.md`. Frontend notes: `.claude/knowledge/contract-notes.md` |
| **Mobile app** | ✅ core verified on the A54: Drive dashboard, alerts, History, Trip summary, Profile, Settings, QR scan. **New:** trip summary **drive chart** (react-native-svg: score line, dangerous/critical shading, moment nodes, picture boxes above critical moments, moment detail sheet) + Drive-screen "last minute" strip from WS `section`, **verified on the A54** (chart, picture box, moment sheet, live strip). Phone fixes verified too: stuck test flash, app-specific settings pages, permission re-check |
| **Web dashboard** | ✅ car-screen mock at `/`: lamp, gauge, level bar, behaviour tiles, seat/sound indicators, red pulse, emergency overlay + siren, summary + **drive chart**, QR "connect phone", simulator panel (`?sim`). **`/trip/:id`** = any stored trip's summary + chart (headless-Chrome screenshot ✅). Build + lint OK |
| Brand / copy | app name only in `config/brand.json` (both apps). Mobile UI copy in `frontend/mobile/src/config/strings.ts` |
| Tooling | ✅ SDK, adb, `android` CLI, JDK 17 toolchain, Ninja swap, Python 3.13 venv, A54 authorized, **Docker Desktop** (Postgres + RustFS via `backend/docker-compose.yml`) |

## How to see it

```bash
cd backend && docker compose up -d                            # Postgres :5433 + RustFS :9000 (no Docker: powershell -File scripts/services.ps1 start)
cd backend && .venv/Scripts/python.exe run.py                 # coordinator + server :8000
backend/.venv/Scripts/python.exe tools/camera_stream.py       # camera: test pattern 10 fps (--video clip.mp4, --webcam "name")
backend/.venv/Scripts/python.exe model/worker.py --fake       # model worker with scripted detections (real one: model/README.md)
curl -s http://127.0.0.1:8000/api/v1/coordinator/status       # camera fps, model, video cache, delivery to the server
cd frontend/mobile && npm start                               # Metro; app already installed on the A54 (dev build with react-native-svg)
adb reverse tcp:8000 tcp:8000 && adb reverse tcp:8081 tcp:8081
cd frontend/dashboard && npm run dev                          # http://localhost:5173 (?sim for the simulator panel, /trip/<id> for a report)
backend/.venv/Scripts/python.exe notebooks/safety_client.py --interval 0.5   # instead of camera + model; or tools/sim.py for exact states
```
**Right now (end of session 5):** backend, camera stream and fake worker run in their own minimized windows, Postgres + RustFS in
Docker, Metro on 8081. A trip started from the phone gets the scripted detections (close the two windows to stop that).

## Next up (in priority order; take one, move it to *In progress* with your name)

1. **Run the real model worker** (`model/README.md`): own venv, `notebooks\setup_models.bat` (YOLO export needs ultralytics, e.g.
   the CV env), a dataset clip through `tools/camera_stream.py --video`. It is the demo path (D34); `risk_pipeline.py --mode prod`
   on the same clip (worker stopped) is only a debug comparison.
2. **Show the new live fields** (types are already re-copied in both apps, `eyes_off_road` has a tile): `speed_kmh` as a speedometer
   ("standing: no penalty" below 5 km/h), optionally the model's `camera.risk` / `alert` colour. Display only, `response` still drives alerts.
3. **Login** + the rest of the report (the drive chart is done; API.md §3–§5; types already re-copied: `TripCreate.driver_id` is now optional, new `User`,
   `AuthOut`, `RegisterIn`, `LoginIn`, `UserUpdate`, `TripReport`, and `ModelReport` / `ModelEpisode` / `ModelAlertEpisode` for the
   new `report.model`, e.g. a "what the camera saw" section: time per alert colour, phone/eyes-off-road episodes on the chart). Login/register screen → store the token, send `Authorization: Bearer`
   on every REST call, on `401` drop it. The Profile screen syncs with `GET/PATCH /auth/me` (username = driverId, display_name = name,
   emergency_contact). Report: the chart + moments exist; add `report.model` ("what the camera saw"). History `GET /trips` with the
   token = my trips.
4. **Video of the whole moment** instead of one image (planned by the user): `VideoCache.frames_between` + `encode_mp4`, clip per
   moment to S3, `video_url` on the moment.
5. **Background/locked alerts on the device:** grant notifications (Settings → Phone setup → Allow), then verify that the foreground service keeps
   the socket alive with the screen off, that the full-screen intent wakes the A54 on `emergency`, and the alarm-channel sound in vibrate mode.
   Log the results in `android-alerting.md` → To verify.
6. **First-run onboarding:** profile + permissions walkthrough (notifications, battery Unrestricted), so a fresh phone is demo-ready in 1 minute.
7. **Release APK** (`npm run android:release`) on the A54, then the demo-phone prep checklist.
8. **Team alignment:** proposals in `contract-notes.md`: dashboard sim panel posting `/telemetry`, SMS on emergency. Phone GPS speed now
   exists as an **opt-in** backend feature (`GET /speed` → `phone_enabled`, then `POST /speed` ~1/s); the app may implement it behind that flag.
9. **Polish:** landscape layout for a dash mount, app icon/splash, haptic patterns per level.
10. **When the server really runs outside the car** (`run.py --role`): outbox on disk (now memory: turning the car off while
    offline loses undelivered sections), and the phone needs two addresses (car for live, server for history) or a reverse proxy.
    Not needed while both run in one process on the laptop. `docs/ARCHITECTURE.md` → Planirano.
11. Stretch: SYSTEM_ALERT_WINDOW bring-to-front during phone use, weekly stats / streaks, driver leaderboard (analytics endpoint).

## In progress

- (nothing)

## Known issues / risks

- **A54 USB link is flaky** (session 5): `adb reverse` emptied by itself, then the device went `offline`/missing while Windows still
  showed "ADB Interface". Replug / re-allow USB debugging, then re-apply `adb reverse`. All permissions are granted on the phone now.
- **"undefined" error after swiping the app away:** not reproduced (logcat clean; with a trip running the process survives via the
  foreground service, without one Android kills it at once). Fixed the likely sources (keep-awake / links / headless handler rejected
  without an Activity). If it comes back, note *where* it prints (Metro terminal or phone).
- **DND row** in Phone setup always shows "Open": no installed library can read `isNotificationPolicyAccessGranted` (needs a tiny
  native module). The other three rows refresh on return from Android settings.
- **With camera + fake worker running, every trip gets scripted detections** (phone at 14–20 s of each minute, etc.). Close their
  windows (or don't start them) when testing something else.
- The dev-client gear button overlaps the top-right status pill. It's dev builds only.
- Web dashboard audio needs one click per page load ("Enable sound"), a browser rule. Its main chunk is 642 KB (Vite warning, harmless).
- `node.exe` is blocked inbound on Public networks (Metro over Wi-Fi / LAN dashboard). USB + `adb reverse` works. Fix: `networking.md`.
- **Windows long paths:** the SDK CMake Ninja was swapped to 1.13.2 (D18). **Android Studio's setup may reinstall CMake**, so re-check
  `cmake/*/bin/ninja.exe --version` afterwards (loop in `environment.md`).
- In-app sounds use media volume (expo-audio has no alarm usage). Only the background notification uses the alarm stream (silent-mode safe).
- Only the live state of the active trip is in the coordinator's memory. History, summaries, sections, reports and logins are on the
  server (Postgres, restart-safe). A trip interrupted by a coordinator crash keeps its summary up to the last section and is closed on
  the next start. While the server is down, sections wait in the coordinator (history/report answer 503).
- **Schema changed (session 5):** `trip_sections` is new and `trips` has `section_s` + `model_report`; `trip_samples` / `risk_events` are
  no longer used. An existing dev Postgres needs a reset (`docker compose down -v` / `services.ps1 reset`; the Docker one on this
  laptop was fresh). No migrations yet: after pulling a change to `backend/app/server/repositories/*.py`, reset (the log names missing columns).
- **Restarting the backend on Windows:** kill the whole process tree; an orphaned uvicorn worker keeps serving old code on :8000
  (`backend/CLAUDE.md` → Zamke). The stale v0.1.0 backend that was running before session 5 was exactly that.
- This laptop also has a **system PostgreSQL 18 service** (`postgresql-x64-18`) on port 5432 with unknown credentials. Ours runs on **5433**
  (Docker or `backend/scripts/services.ps1`). Without them the live path still works, the server answers 503 (log says so).
- CV: hand detection is weak in the dark night clips (`05_23_62_0101xx`, no hands seen in ~37% of frames). Sunglasses make the eye
  blendshapes meaningless. YOLO sees a phone in only ~30% of frames of a texting clip (hence the decaying memory). Details: `cv-pipeline.md`.


## Open questions

- **CV:** the model has no `looking_behind` / `turning_around` output (only the simulator sends them). Will the CV team add one?
  The models run live through the coordinator (`model/worker.py`). Open: is the in-car CPU fast enough
  (~110 ms per processed frame on this laptop vs a 100 ms budget at every 3rd frame)?
- **Production split:** coordinator (car) and server (reports) are separated in code (`docs/ARCHITECTURE.md`). Open: a reverse proxy
  so the phone keeps one address when they run apart, image access (signed URLs instead of the demo's public bucket), retention,
  several cars (`car_id`).
- **Emergency contact:** the backend only logs. The app offers Text/Call buttons on the emergency screen. Should the backend send SMS itself?
- **Dashboard sim panel** posting `/telemetry` during demos: OK with the backend owner?
- **Accounts:** login is optional for now (trips without a token still work). Should the app require it? No password reset/change yet.

## Manual steps only a human can do

- [x] Authorize USB debugging on the A54 · [x] Allow Python through the firewall
- [x] On the A54: Settings tab → Phone setup → Notifications, Unrestricted battery, DND (all allowed, session 5)
- [ ] Replug the A54 USB cable (the link kept dropping at the end of session 5)
- [ ] Android Studio install: when asked for the SDK location, choose the existing `%LOCALAPPDATA%\Android\Sdk`
- [x] Docker Desktop installed (session 5): Postgres + RustFS run from `backend/docker-compose.yml` on this laptop
- [ ] Optional (admin): remove the `node.exe` Block firewall rules (`networking.md`)

## Session log

- 2026-11-06, session 1: toolchain setup (Android SDK + `android` CLI, JDK 17 toolchain, Python 3.13, Ninja long-path fix), Expo SDK 58
  scaffold with all native modules, web starter imported, `.claude/` knowledge base. The backend landed (`903df76`), so the docs were realigned
  to `docs/API.md`. The dev build was verified on the A54.
- 2026-11-06, session 2: mobile app core (API client, stores, alert engine, overlays, 6 screens) verified on the A54 with the real
  backend via `tools/sim.py`: warning flash + beeps, emergency siren screen, I'm OK, trip end → summary. Web car-screen dashboard
  built by a sub-agent (verified in Chrome on its own backend). `config/brand.json` is the single app-name source.
- 2026-11-06, Claude (backend, for Matija Vujić): `POST /telemetry` accepts the CV model's frame record (`frame`, `perception` dropped).
  Active categories are mapped to labels and scored, and risk/alert/categories go to the app as `TripState.camera`. The model's red alert
  forces vibration + loud sound at any level while moving. New label `eyes_off_road` (weight 1.0). `safety_client.py`: `send_frame`,
  `--replay frames.jsonl`. Verified: 32 tests, plus a synthetic replay → WS (40/42 messages carried `camera`, no `perception`). docs/API.md updated.
- 2026-11-06, Claude (backend storage, for Matija Vujić): trip recording next to the live path. Postgres (`trips`, `trip_samples` per 1 s
  with the model's numbers + speed, `risk_events`) and RustFS S3 (H.264 clip 3 s before / 2 s after each risky moment + thumbnail, public
  bucket for the demo). New routes `/trips/{id}/timeline`, `/trips/{id}/events`, `/media/{key}`, `/video/frames`, `/speed`. Speed is
  mocked by the backend (6 Bezier scenarios, random per trip); phone GPS is opt-in (`PHONE_SPEED_ENABLED`). Portable Postgres 18.6 + RustFS 1.0.4
  without Docker (`backend/scripts/services.ps1`) plus `docker-compose.yml`. Verified: 56 tests (40× repeat after a CREATE TABLE race fix),
  real-time runs with video on real Postgres + RustFS, Postgres/RustFS stopped mid-drive (live path unaffected, rows flushed once back).
- 2026-11-06, Claude (alignment after the frontend pull, for Matija Vujić): model categories come from `risk_config.json`, so
  `eyes_closed` → `drowsy`, `eating_drinking` is ignored, and the guessed names are gone (`services/camera.py` + `tests/test_camera_mapping.py`,
  which fails on an unknown category). `hands_off_wheel` confirmed as "no hand on the wheel". Both apps re-copied §4 types, and
  `eyes_off_road` got a tile. `.gitignore` now covers CV models, pipeline logs and cabin videos. Verified: 59 backend tests, mobile
  typecheck + lint, dashboard `tsc -b` + lint + vite build.
- 2026-11-06, Claude (for Matija Vujić): Node on the backend laptop upgraded 22.11 → 26.13.0 LTS (winget), same as the frontend
  laptop. Clean `npm ci` in both apps, dashboard build, mobile typecheck + lint all pass there now.
- 2026-11-06, Claude (accounts + trip report, for Matija Vujić): reviewed the frontend (summary/history/profile: no login, history from
  backend memory) and the storage. Added `users` + `user_sessions` (scrypt password hash, random 30-day bearer tokens, only their SHA-256
  stored), `/auth/register|login|logout|me`, trips owned by the logged-in account (others get 404), history and summary from Postgres
  (restart-safe), a running trip summary every ~10 s plus closing trips left open by a crash, and `GET /trips/{id}/report` (summary + user +
  raw per-second samples + moments with images/clips) so the app computes its own charts. New `docs/DATABASE.md` (schema, what the front
  gets, review). Verified: 68 tests (25× repeat), real Postgres + RustFS: register → owned trip with video → report → backend restart
  (token, history, report intact) → hard kill mid-trip (trip closed on restart with its last summary).
- 2026-11-06, session 3 (CV pipeline, for ttcpavle): `risk_pipeline.py` fixed to watch the driver (right side), head_roi face crop,
  calibration clamped to a measured prior, look-down/eyes-closed retune, yolo11s/640, hands evidence, unique log folders, `--show` diagnostic
  panel + `--save-video/--verbose/--log-all/--pick-roi/--calibrate`. Category names unchanged (backend mapping still valid). Run on all 56 clips.
- 2026-11-06, session 4 (CV pipeline for deployment, for ttcpavle): the trip-level part of the pipeline (summary, behaviour episodes,
  alert episodes) moved to `backend/app/services/model_report.py`, fed by the `/telemetry` frame stream, stored in `trips.model_report`
  and returned as `TripReport.model` (API.md, DATABASE.md updated). `risk_pipeline.py` keeps per-frame math only and got `--mode dev`
  (reduced overlay in `dev_overlay.py`) and `--mode prod` (headless `BackendSink`, real-time pacing for files, `--start-trip`).
  Verified: 76 backend tests; new engine identical to the old on 18 020 steps; backend report equals the old summary/events on 62
  recorded runs (up to rounding); dev run on a clip + screenshot; prod run on a clip against a live backend (SQLite) → report with
  `model` (35 ticks, 0 errors).
- 2026-11-06, session 5 (Claude, for Matija Radović): **phone fixes** verified on the A54: test alerts no longer overwrite the live trip
  (double "Test warning" kept the red flash on forever; now a Stop toggle, and live flashing stops after 3 s without `state`); Phone
  setup opens this app's own Android pages (was: all-apps lists; our code, not the dev build); permissions re-check on return + pull to
  refresh + a refresh button after Open; keep-awake/links/headless handler can't reject without an Activity. **Backend split** into
  coordinator + server (`docs/ARCHITECTURE.md`): camera WS, model worker link, extracted `RiskEngine` (identical to the CV original),
  5 min diskcache video cache, 2 s sections with danger + image → WS `section` + server via an outbox; server stores `trip_sections` +
  images, report = sections + moments (+ the CV team's `model` report, merged from their parallel commit and now fed by the coordinator).
  `model/worker.py` (+ `--fake`), `tools/camera_stream.py`, `model/Dockerfile` (untested). Mobile + dashboard drive charts, dashboard
  `/trip/:id`. Postgres + RustFS moved to Docker here. Verified: 89 backend tests, live run camera → fake worker → coordinator →
  Postgres/RustFS (66 sections, 9 moments with images), dashboard chart screenshot, mobile + dashboard typecheck/lint/build.
  The new mobile screens were checked on the A54 at the end (after the USB link came back; a cold Metro bundle takes ~70 s).
  Not verified: the real model worker (no models here).
- 2026-11-06, session 6 (Claude, for Matija): **architecture checked against the user's definition** (car = camera + model +
  coordinator, server outside; video only into the coordinator; coordinator owns caching, server owns Postgres + RustFS). It held
  (no DB/S3 import in the coordinator, none of the coordinator in the server); fixed the gaps: `/telemetry` frame records
  (`--mode prod`) are a **debug feed**, refused with 409 while a model worker is connected and counted in `/coordinator/status`;
  `POST /trips` with a token **no longer 503s when the server is unreachable** (stale-if-error token cache, else
  `TripMeta.owner_token` resolved by the server); video frames also expire on housekeeping. `setup_models.bat`/`.sh` resolved
  (+ `.gitattributes`: bat CRLF, sh LF). Docs: ARCHITECTURE (real vs debug paths, rolling-window cache, owner_token), API.md,
  root CLAUDE.md, D34. Verified: 92 backend tests (new ones 8× repeated), `setup_models.bat` downloads + package stop in cmd.
