# PROGRESS

> Live status board for humans and agents. **Read it first, update it last** (`.claude/rules/progress.md`).
> Keep it short and link to files. Details belong in `.claude/knowledge/`. Domain rules: root `CLAUDE.md`. Contract: `docs/API.md`.
> Last updated: 2026-11-07 ~11:50, session 10: Dušan's model merged into main and tested end to end with dataset clips (Claude, for Matija).

## Snapshot

| area | state |
|---|---|
| Backend (FastAPI) | ✅ **two parts** (`docs/ARCHITECTURE.md`), one process on :8000 (`python run.py`; split with `--role` + `SERVER_URL`). **Coordinator** (`app/coordinator`): phone WS, camera stream (`WS /camera/ws`, `POST /video/frames`), **model worker link** (`WS /model/ws`), the CV team's `RiskEngine` (extracted, identical to the original: test), score + car response, **5 min video cache** (diskcache), a **section summary every 2 s** (score, what was seen, `danger`, image of the riskiest frame when dangerous) to the phone (WS `section`) and to the server (outbox, retries while it's down), plus the camera model's trip report (`app/services/model_report.py`). **Checked against the user's definition (session 6):** the car = camera + model + coordinator, the server is outside; `/telemetry` frame records are a debug feed (409 while a model worker is connected), a phone login never blocks the car (offline: stale token cache, or the token rides along as `TripMeta.owner_token`). **Server** (`app/server`): accounts, Postgres (`trips`, `trip_sections`) + RustFS images, history, **`GET /trips/{id}/report`** = summary + user + sections + **moments** (merged dangerous sections with an image) + `model`. 92 tests. Speed is mocked by the coordinator (phone GPS opt-in). **Session 7: the score is live** (D35: danger now × speed factor, falls and recovers within seconds, nothing while standing), summaries headline `average_score`. 95 tests. **Session 10:** collapse (score 0 + emergency at once, also standing still) and one camera (Dušan, D45); 105 tests + 38 gateway tests |
| **Car link (Bluetooth)** | ✅ **session 9, D38–D42:** phone ↔ car over **Bluetooth LE** (default; WebSocket over Wi-Fi/USB is the fallback in Settings → Car connection), phone ↔ server over HTTP(S) at its **own address** (gear on the login screen; `localhost:8001` over USB, laptop IP:8001 on the hotspot, later an ngrok link). Laptop: `backend/coordinator/car_link/gateway.py` (own process, pywinrt GATT server, bridges the coordinator's WS + [K] REST; coordinator unchanged). Phone: local Expo module `modules/car-link` + `src/api/carlink.ts`. Protocol: `docs/BLUETOOTH.md` (frames ≤ 244 B, indications, state coalescing, 2 s ping / 7 s watchdog). **Verified on the A54:** permission flow, connect (~10 s from cold start), start trip (201), live score + sections (180 msgs, 0 lost), end trip (200) → summary + report from the server on :8001, reconnect after a gateway restart (~10 s) and after phone Bluetooth off/on (~4 s). 38 tests in `backend/coordinator/car_link` |
| Camera + model | ✅ **Dušan's `rivian_model/` is the model (session 10, D44)**: own venv `rivian_model/.venv` (Python 3.13, CPU torch), weights via `setup_models.py`, ~40 ms per frame here, every frame of the 10 fps stream. Camera: `tools/camera_stream.py` (clip / webcam) or `rivian_model/klip_po_voznji.py` (each trip = next dataset clip). **Verified with dataset clips:** 6 REST runs (phone, texting, calm, collapse → emergency at 13.8 s), the A54 over Bluetooth (collapse overlay, phone critical, summaries with pictures, history) and the dashboard overlay. `demo.ps1` starts the whole car. Book: `cv-pipeline.md` |
| Simulators | ✅ `notebooks/safety_client.py` (full demo drive, `--replay frames.jsonl`, `--video 0` streams the webcam so dangerous moments get images, `--backend-speed`) + `tools/sim.py` (exact states, see skill `backend-local`) |
| CV models | **Removed (session 10, D44):** the CV team's `risk_pipeline.py`, `dev_overlay.py`, `setup_models.*` and `model/worker.py` (restore: `git show 8d05c97:<path>`). `notebooks/risk_config.json` stays, trimmed to what the coordinator's `RiskEngine` reads, plus `collapse` |
| Contract | ✅ `docs/API.md` (source of truth; §5 tags each route [K] coordinator / [S] server). New: WS `section`, report `sections` + `moments` (+ `model`). Internal contracts: `docs/ARCHITECTURE.md`. Frontend notes: `.claude/knowledge/contract-notes.md` |
| **Mobile app** | ✅ **UX pass (session 8, D37), verified on the A54:** boot check behind the splash (session + first link answer, no stale/offline flash), keyboard-aware screens (react-native-keyboard-controller) with Next/Go chaining + show/hide password, login without any car-computer UI (own Connection screen; "Change address" only when the server is unreachable), Settings with a car-computer row + one-style Phone setup (DND read by our own module `modules/system-access`) + "Open system app settings", Profile with equal Save/Log out, placeholders that say what to type, tab bar without ripple/shadow, system nav bar in the tab bar colour. ✅ **Accounts (session 7, D36):** login / create-account screen first (with the car-computer address), token on every call, 401 → login, Profile = account (name, emergency contact, log out), History = my trips, summary/history headline the average. Verified on the A54: register → start → mocked drive (critical with the phone, safe ~6 s later) → end → summary + chart → history → logout → wrong password → login. ✅ core verified on the A54: Drive dashboard, alerts, History, Trip summary, Profile, Settings, QR scan. **New:** trip summary **drive chart** (react-native-svg: score line, dangerous/critical shading, moment nodes, picture boxes above critical moments, moment detail sheet) + Drive-screen "last minute" strip from WS `section`, **verified on the A54** (chart, picture box, moment sheet, live strip). Phone fixes verified too: stuck test flash, app-specific settings pages, permission re-check |
| **Web dashboard** | ✅ car-screen mock at `/`: lamp, gauge, level bar, behaviour tiles, seat/sound indicators, red pulse, emergency overlay + siren, summary + **drive chart**, QR "connect phone", simulator panel (`?sim`). **`/trip/:id`** = any stored trip's summary + chart (headless-Chrome screenshot ✅). Build + lint OK |
| Brand / copy | app name only in `config/brand.json` (both apps). Mobile UI copy in `frontend/mobile/src/config/strings.ts` |
| Tooling | ✅ SDK, adb, `android` CLI, JDK 17 toolchain, Ninja swap, Python 3.13 venv, A54 authorized, **Docker Desktop** (Postgres + RustFS via `backend/docker-compose.yml`) |

## How to see it

```powershell
.\demo.ps1 -PoVoznji -NoBle   # whole car, one window per part: Docker storage, server :8001, coordinator :8000 (cruise), model (05_23),
                              # per-trip clips; without -NoBle it also starts the Bluetooth gateway
# the pieces, from the repo root:
cd backend; docker compose up -d                                                        # Postgres :5433 + RustFS :9000
cd backend; .venv\Scripts\python.exe run.py --role server --port 8001 --no-reload        # server (accounts, history, report)
cd backend; $env:SERVER_URL='http://127.0.0.1:8001/api/v1'; $env:SPEED_SCENARIO='cruise'; .venv\Scripts\python.exe run.py --role coordinator --no-reload
rivian_model\.venv\Scripts\python.exe rivian_model\rivian_detector.py --camera 05_23     # the model (setup once: rivian_model/README.md)
backend\.venv\Scripts\python.exe rivian_model\klip_po_voznji.py                        # each phone trip = next clip (or tools\camera_stream.py --video <clip>)
backend\.venv\Scripts\python.exe backend\coordinator\car_link\gateway.py --name "Rivian demo car"   # Bluetooth (docs/BLUETOOTH.md)
curl -s http://127.0.0.1:8000/api/v1/coordinator/status                                   # camera fps, model, video cache, server delivery
cd frontend/mobile; npm start; npm run adb:reverse                                        # Metro + USB ports 8081/8000/8001
cd frontend/dashboard; npm run dev                                                        # http://localhost:5173 (?sim, /trip/<id>)
```
**Right now (2026-11-07, ~11:50):** in their own windows: server :8001, coordinator :8000 (cruise), the model (`demo: model (05_23)`),
the per-trip camera (`demo: kamera (klip po voznji)`, list 031246 collapse, 021254 phone, 005853 phone in the lap), plus the user's
Bluetooth gateway tab, Metro and Docker. The A54 is logged in as `matija` (`secret123`), car link Bluetooth, server `localhost:8001`
over USB (adb reverse re-applied). The old `--mock` coordinator and the old server were stopped with the user's OK.

## Next up (in priority order; take one, move it to *In progress* with your name)

1. **Dockerize every part** (user's next step: start only on the user's go): images for server, coordinator, model
   (`rivian_model/Dockerfile`, verified by Dušan: ~3 GB because Ultralytics pulls torch; ONNX Runtime alone would be ~1 GB) and
   dashboard, one compose with Postgres + RustFS, so every PC runs the car with one command. The Bluetooth gateway stays on the Windows
   host (it needs the radio). Camera series (`--camera`) and the dataset folder become compose settings.
2. **Release APK** (user's next step): `npm run android:release`, or Dušan's verified recipe in README.md (short folder,
   `CMAKE_OBJECT_PATH_MAX=250`); on the phone Bluetooth on + Nearby devices allowed, server address set.
3. **Backend folder split** (user's request, decide together with Docker): Fork A's WIP is local branch
   `worktree-agent-a336269a95214247a` (`backend/coordinator/`, `backend/server/`, `backend/shared/`, `start.ps1`); left: tests, dashboard
   with two targets + QR `driveralert://connect?server=…&car=…` (the app already parses it), `safety_client.py --server`, docs. It
   predates the Bluetooth gateway and the model.
4. **Show the new live fields** (types are already in both apps): `speed_kmh` as a speedometer ("standing: no warnings" below 5 km/h),
   optionally the model's `camera.risk` / `alert` colour. Display only, `response` still drives alerts.
5. **The rest of the report:** `report.model` ("what the camera saw": time per alert colour, phone/eyes-off-road/collapse episodes on
   the chart). Maybe: password change, a "logged in as" chip on the dashboard.
6. **Video of the whole moment** instead of one image (planned by the user): `VideoCache.frames_between` + `encode_mp4`, clip per
   moment to S3, `video_url` on the moment.
7. **Background/locked alerts on the device:** verify that the foreground service keeps the link alive with the screen off, that the
   full-screen intent wakes the A54 on `emergency`, and the alarm-channel sound in vibrate mode (`android-alerting.md` → To verify).
8. **First-run onboarding:** profile + permissions walkthrough, so a fresh phone is demo-ready in 1 minute.
9. **Team alignment:** proposals in `contract-notes.md` (dashboard sim panel posting `/telemetry`, SMS on emergency). Phone GPS speed
   exists as an **opt-in** backend feature (`GET /speed` → `phone_enabled`, then `POST /speed` ~1/s).
10. **Polish:** landscape layout for a dash mount, app icon/splash, haptic patterns per level, the dashboard QR for the split addresses.
11. **When the server really runs outside the car:** outbox on disk, and the phone's two addresses or a reverse proxy
    (`docs/ARCHITECTURE.md` → Planirano).
12. Stretch: SYSTEM_ALERT_WINDOW bring-to-front during phone use, weekly stats / streaks, driver leaderboard (analytics endpoint).

## In progress

- (nothing)

## Known issues / risks

- **Bluetooth:** frames stay ≤ 244 B (514-B notifications never arrived on this laptop), rx uses indications (notifications got lost
  while the phone wrote), no encryption yet (anyone in range can read the stream or call [K] routes), Windows rotates its advertising
  address (the app always scans first). Details: `docs/BLUETOOTH.md`.
- Until the folder split lands, the server address :8001 needs the extra `run.py --role server --port 8001`; the dashboard's QR still
  shows the old single address.

- **A54 USB link is flaky** (session 5): `adb reverse` emptied by itself, then the device went `offline`/missing while Windows still
  showed "ADB Interface". Replug / re-allow USB debugging, then re-apply `adb reverse`. All permissions are granted on the phone now.
- **"undefined" error after swiping the app away:** not reproduced (logcat clean; with a trip running the process survives via the
  foreground service, without one Android kills it at once). Fixed the likely sources (keep-awake / links / headless handler rejected
  without an Activity). If it comes back, note *where* it prints (Metro terminal or phone).
- **The model's driver zone is per camera series** (`--camera 05_23|08_14`): clips of the other series give wrong detections.
  `demo.ps1` takes it from the clip name, `klip_po_voznji.py` refuses a mixed list. While `klip_po_voznji.py` runs, every phone
  trip gets the next clip (then none).
- **Teammates:** the CV team's `notebooks/risk_pipeline.py`, `setup_models.*` and `model/worker.py` are gone from main (D44); a local
  change to them conflicts as modify/delete. Restore with `git show 8d05c97:<path>`.
- A server started before session 10 rejects `collapse` sections (422, the outbox retries forever): restart :8001 on the new code.
  `adb kill-server` (or an unauthorized phone) drops the `adb reverse` ports: re-run `npm run adb:reverse`.
- Ports **8685–8884 are reserved** on this laptop (WinError 10013): Dušan's test defaults 8765/8766 fail here, use e.g. 8020.
- The dev-client gear button floats over the right edge mid-screen (covers e.g. the DND "Allow" button). Dev builds only; drag it away.
- The splash image is still Expo's default logo (`assets/images/splash-icon.png`), not the app's. Polish item (Next up #9).
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
- Model limits (Dušan, `rivian_model/ATRIBUTI.md` §4): misses a phone in the lap in the dark, glances < 2 s and a phone on the console
  YOLO can't see; collapse is late when the pose can't find a person lying on the wheel (022338); sunglasses make the eye signals
  meaningless. Details: `cv-pipeline.md`.


## Open questions

- **Model:** no `looking_behind` / `turning_around` / `hands_off_wheel` output (only the simulators send them). Fast enough on laptops
  (~40 ms per frame here, ~73 ms on Dušan's i5); the in-car CPU is unknown. The camera doesn't say which series it is, so the driver
  zone is a model start option.
- **Production split:** coordinator (car) and server (reports) are separated in code (`docs/ARCHITECTURE.md`). Open: a reverse proxy
  so the phone keeps one address when they run apart, image access (signed URLs instead of the demo's public bucket), retention,
  several cars (`car_id`).
- **Emergency contact:** the backend only logs. The app offers Text/Call buttons on the emergency screen. Should the backend send SMS itself?
- **Dashboard sim panel** posting `/telemetry` during demos: OK with the backend owner?
- **Accounts:** decided: the app requires login (D36); the backend still accepts token-less trips (simulator, dashboard). No password reset/change yet.

## Manual steps only a human can do

- [x] Authorize USB debugging on the A54 · [x] Allow Python through the firewall
- [x] On the A54: Settings tab → Phone setup → Notifications, Unrestricted battery, DND (all allowed, session 5; DND was found off
  in session 8 and switched on again: its confirmation dialog needs "Allow")
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
- 2026-11-07, session 7 (Claude, for Matija): **live score** (D35, user's request: "score is not gamification, it goes up and down; speed
  scales the danger; at 0 km/h nothing warns"): danger of the behaviours seen now (growing with duration) or the CV model's risk ×
  speed factor (0 standing, 1 at 50, 1.6 at 130) × night; falls in ~1 s, back to safe ~6 s after; vibration/sound only while something
  risky happens; emergency needs 2 s; summaries headline `average_score` (moving time), `level` = its level. Calibrated on the fake
  worker at fixed speeds and live on the A54. **Accounts in the app** (D36): login/register screen with the address, token on every call,
  401 → login, Profile = account + logout, History = my trips; the app drops a trip the car no longer runs (backend restart) and "End" on
  it opens the stored summary. **`run.py --mock`**: backend + mocked camera + fake model in one window; the mocks live in their own
  process group (uvicorn's reload Ctrl+C killed them). Dashboard summary card = average + lowest. Docs: API.md (§3 login, §4 summary
  comments re-copied into both apps, §7 score + levels), root CLAUDE.md, ARCHITECTURE, metrics-and-scoring, contract-notes, decisions,
  backend README/CLAUDE.md, skills. Verified: 95 backend tests, mobile typecheck + lint, dashboard tsc + lint, the full phone flow.
- 2026-11-07, session 8 (Claude, for Matija): **phone UX pass** after the user's review (D37). Boot check: native splash until the
  saved session is checked (`/auth/me`) and the car's first answer is in, so a cold start opens straight in its real state (recorded
  before/after on the A54: the "Car computer offline" flash is gone); offline start keeps the session. Keyboard: react-native-keyboard-controller
  `KeyboardAwareScrollView` in every `Screen`, Next/Go field chaining, show/hide password, inline validation. Login without the
  car-computer box (address on its own Connection screen with explained QR/USB rows; "Change address" in the error when unreachable).
  Settings: car-computer row, Phone setup rows all alike (DND now read by the new local Expo module `modules/system-access`; it
  revealed DND was actually off), white "Open system app settings". Profile: equal Save/Log out in separate sections, Save only when
  changed. Tab bar: no ripple circle, no elevation; `expo-navigation-bar` `enforceContrast: false` (nav area now #171717 = tab bar,
  was a 40 % black scrim). Copy: no brackets, descriptive placeholders. Native rebuild done (first try hit a Gradle DNS hiccup).
  Verified: mobile typecheck + lint, every changed screen on the A54 (screenshots), cold start online/offline, logout/login with
  the keyboard, unreachable-server path, test warning. Docs: rules/mobile.md (UI kit rules), architecture, android-alerting (DND
  dialog + channel bypass), decisions D37, mobile-dev + android-device skills.
- 2026-11-07, session 9 (Claude, for Matija): car vs cloud discussion (user: Bluetooth as the main car link, hotspot only for the
  server, maybe ngrok later). **Bluetooth car link** end to end: laptop gateway (pywinrt GATT server, coordinator unchanged) + phone Expo
  module + transport, Bluetooth default with Wi-Fi fallback; hardware fixes (244-B frames, indications, coalescing, ping/watchdog,
  adapter broadcast, always scan). Fork C: the app's server address (gear on login, Server screen, QR + deep link). Fork A: backend
  folder split, stopped by the usage limit (WIP branch, Next 1). Docs: BLUETOOTH.md, D38–D42, environment, android-device skill,
  metro.config.js. Verified on the A54 (Car link row); mobile typecheck + lint, 38 gateway tests.
- 2026-11-07, session 9b (Claude, for Matija): verified the fully split run (server :8001 alone, coordinator `--role coordinator`
  with `SERVER_URL` + mocks, gateway from `backend/.venv`): register 201, trip 201/200, the server's report has the sections.
  Run commands fixed in PROGRESS, docs/BLUETOOTH.md and skill `backend-local`.
- 2026-11-07, session 9c (Claude, for Matija): **manual car pick** (D43): Car connection → Cars nearby lists what the scan
  hears (the laptop shows as `DESKTOP-5VRFVCB`) with Connect; Disconnect / "Connect to <car>"; the phone reconnects by itself
  only to the car the driver connected to. Verified on the A54: list, tap → connected in ~7 s, Disconnect stays off, Connect
  to the remembered car in ~5 s (found by its advertised name after an address change). Typecheck + lint pass.
- 2026-11-07, session 10 (Claude, for Matija): **Dušan's model merged into main** (D44/D45). His 9 `nas-demo` commits cherry-picked
  (author kept, AI trailers stripped; the tree equals a real merge): `rivian_model/` (YOLO11n + pose + MediaPipe face, a detector on the
  coordinator's model protocol), collapse end to end (score 0 + emergency at once, also standing; app + dashboard copy), one camera.
  Removed the CV team's worker, pipeline and setup scripts and `run.py --mock`; `risk_config.json` trimmed. `demo.ps1` rewritten for
  main (server :8001, coordinator :8000, Bluetooth gateway, model, camera). Model venv (Python 3.13, CPU torch) + weights installed.
  Verified: 105 backend + 38 gateway tests, mobile typecheck + lint, dashboard tsc + lint + build, the offline detector test (same
  numbers as Dušan's), 6 live REST runs on dataset clips (phone, texting, calm, collapse → emergency at 13.8 s), the A54 over
  Bluetooth (3 trips: collapse overlay, phone critical, summaries with pictures, history) and the dashboard overlay. Docs: README,
  root + agent CLAUDE.md, ARCHITECTURE, API, BLUETOOTH, backend docs, knowledge books (cv-pipeline rewritten), backend-local skill.
