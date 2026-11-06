# PROGRESS

> Live status board for humans and agents. **Read it first, update it last** (`.claude/rules/progress.md`).
> Keep it short and link to files. Details belong in `.claude/knowledge/`. Domain rules: root `CLAUDE.md`. Contract: `docs/API.md`.
> Last updated: 2026-11-06, alignment after the frontend pull (Claude, for Matija Vujić).

## Snapshot

| area | state |
|---|---|
| Backend (FastAPI) | ✅ working (teammate Matija Vujić). 59 tests pass. Accepts the CV model's frame records (`TripState.camera`); every category in `risk_config.json` is mapped or deliberately ignored (`eyes_closed` → `drowsy`). **Records every trip** to Postgres + RustFS (S3): 1 s samples, risky moments with MP4 clips → `GET /trips/{id}/timeline`, `/events`, `/media/...`. **Speed comes from the backend** (mock drive, Bezier scenarios; phone GPS via `POST /speed` is opt-in, off) |
| Simulators | ✅ `notebooks/safety_client.py` (full demo drive, `--replay frames.jsonl`, `--video 0` streams the webcam so risky moments get clips, `--backend-speed`) + `tools/sim.py` (exact states, see skill `backend-local`) |
| CV models | `notebooks/risk_pipeline.py` + `risk_config.json` landed (ttcpavle). Output format known (`frames.jsonl` records: categories, risk, alert). Bridge: `SafetyClient.send_frame(rec)` + `send_video_frame(frame)` (no speed). Not yet called live from the pipeline |
| Contract | ✅ `docs/API.md` (source of truth). Frontend notes and verification: `.claude/knowledge/contract-notes.md` |
| **Mobile app** | ✅ **core done and verified on the A54 against the real backend**: Drive dashboard, alerts (flash, sound, vibration, voice, emergency siren screen), History, Trip summary, Profile, Settings (address/test/QR, toggles, test alerts, phone setup), QR scan |
| **Web dashboard** | ✅ car-screen mock at `/`: lamp, gauge, level bar, behaviour tiles, seat/sound indicators, red pulse, emergency overlay + siren, summary, QR "connect phone", simulator panel (`?sim`). Build + lint OK |
| Brand / copy | app name only in `config/brand.json` (both apps). Mobile UI copy in `frontend/mobile/src/config/strings.ts` |
| Tooling | ✅ SDK, adb, `android` CLI, JDK 17 toolchain, Ninja swap, Python 3.13 venv, A54 authorized |

## How to see it

```bash
cd backend && powershell -File scripts/services.ps1 start     # Postgres :5433 + RustFS :9000 (portable, no Docker; `install` once)
cd backend && .venv/Scripts/python.exe run.py                 # backend :8000
cd frontend/mobile && npm start                               # Metro; app already installed on the A54 (dev build)
adb reverse tcp:8000 tcp:8000 && adb reverse tcp:8081 tcp:8081
cd frontend/dashboard && npm run dev                          # http://localhost:5173 (?sim for the simulator panel)
backend/.venv/Scripts/python.exe notebooks/safety_client.py --interval 0.5   # or tools/sim.py for exact states
```

## Next up (in priority order; take one, move it to *In progress* with your name)

1. **Show the new live fields** (types are already re-copied in both apps, `eyes_off_road` has a tile): `speed_kmh` as a speedometer
   ("standing: no penalty" below 5 km/h), optionally the model's `camera.risk` / `alert` colour. Display only, `response` still drives alerts.
2. **Trip report screen** (API.md §5 + §7 "Izveštaj"): score/speed chart from `GET /trips/{id}/timeline`, "worst moments" from
   `GET /trips/{id}/events?order=worst` with thumbnail + `video_url` playback (expo-video). Hide the button on `503` (recording down).
3. **Background/locked alerts on the device:** grant notifications (Settings → Phone setup → Allow), then verify that the foreground service keeps
   the socket alive with the screen off, that the full-screen intent wakes the A54 on `emergency`, and the alarm-channel sound in vibrate mode.
   Log the results in `android-alerting.md` → To verify.
4. **First-run onboarding:** profile + permissions walkthrough (notifications, battery Unrestricted), so a fresh phone is demo-ready in 1 minute.
5. **Release APK** (`npm run android:release`) on the A54, then the demo-phone prep checklist.
6. **Team alignment:** proposals in `contract-notes.md`: dashboard sim panel posting `/telemetry`, SMS on emergency. Phone GPS speed now
   exists as an **opt-in** backend feature (`GET /speed` → `phone_enabled`, then `POST /speed` ~1/s); the app may implement it behind that flag.
7. **Polish:** landscape layout for a dash mount, app icon/splash, haptic patterns per level.
8. Stretch: SYSTEM_ALERT_WINDOW bring-to-front during phone use, weekly stats / streaks, driver leaderboard (analytics endpoint).

## In progress

- (nothing)

## Known issues / risks

- **Notification permission isn't granted yet** on the A54. Background warnings and emergency notifications fail (logged as
  `[notify] … POST_NOTIFICATIONS`). Fix: Settings → Phone setup → Notifications → Allow, or start a trip with the in-app Start button (it asks).
- The dev-client gear button overlaps the top-right status pill. It's dev builds only.
- Web dashboard audio needs one click per page load ("Enable sound"), a browser rule. Its main chunk is 642 KB (Vite warning, harmless).
- `node.exe` is blocked inbound on Public networks (Metro over Wi-Fi / LAN dashboard). USB + `adb reverse` works. Fix: `networking.md`.
- **Windows long paths:** the SDK CMake Ninja was swapped to 1.13.2 (D18). **Android Studio's setup may reinstall CMake**, so re-check
  `cmake/*/bin/ninja.exe --version` afterwards (loop in `environment.md`).
- In-app sounds use media volume (expo-audio has no alarm usage). Only the background notification uses the alarm stream (silent-mode safe).
- Active trips and `GET /trips` / `/summary` still live in backend memory: after a restart, old trip ids give 404 there. The report
  (`/timeline`, `/events`, clips) is in Postgres + S3 and survives.
- This laptop also has a **system PostgreSQL 18 service** (`postgresql-x64-18`) on port 5432 with unknown credentials. Ours runs on **5433**
  (`backend/scripts/services.ps1`). Without `services.ps1 start` the backend still works, it just records nothing (log says so).


## Open questions

- **CV:** the model has no `looking_behind` / `turning_around` output (only the simulator sends them). Will the CV team add one?
  `risk_pipeline.py` doesn't call `SafetyClient.send_frame` yet, so the models don't run live against the backend.
- **Production storage:** split the in-car compute server from a report server the driver can reach away from the car? Clip access
  (signed URLs instead of the demo's public bucket) and retention are still open.
- **Emergency contact:** the backend only logs. The app offers Text/Call buttons on the emergency screen. Should the backend send SMS itself?
- **Dashboard sim panel** posting `/telemetry` during demos: OK with the backend owner?
- **DB work:** will trips get user accounts (real login), or stay keyed by `driver_id`? (Profile is a local stand-in.)

## Manual steps only a human can do

- [x] Authorize USB debugging on the A54 · [x] Allow Python through the firewall
- [ ] On the A54: Settings tab → Phone setup → **Notifications: Allow**, **Unrestricted battery: Allow**, **DND: Open → allow**
- [ ] Android Studio install: when asked for the SDK location, choose the existing `%LOCALAPPDATA%\Android\Sdk`
- [x] ~~Docker Desktop + WSL~~ not needed: Postgres + RustFS run portable from `%LOCALAPPDATA%\safety-reviewer` (`backend/scripts/services.ps1`)
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
