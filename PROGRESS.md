# PROGRESS

> Live status board for humans and agents. **Read it first, update it last** (`.claude/rules/progress.md`).
> Keep it short and link to files. Details belong in `.claude/knowledge/`. Domain rules: root `CLAUDE.md`. Contract: `docs/API.md`.
> Last updated: 2026-11-06, session 2 (Claude, for Matija Radović).

## Snapshot

| area | state |
|---|---|
| Backend (FastAPI) | ✅ working (teammate Matija Vujić). Teammate is adding Postgres + MinIO (Docker expected) |
| Simulators | ✅ `notebooks/safety_client.py` (full demo drive) + `tools/sim.py` (exact states, see skill `backend-local`) |
| CV models | manual / not integrated |
| **Mobile app** | ✅ **core done and verified on the A54 against the real backend**: Drive dashboard, alerts (flash, sound, vibration, voice, emergency siren screen), History, Trip summary, Profile, Settings (address/test/QR, toggles, test alerts, phone setup), QR scan |
| **Web dashboard** | ✅ car-screen mock at `/`: lamp, gauge, level bar, behaviour tiles, seat/sound indicators, red pulse, emergency overlay + siren, summary, QR "connect phone", simulator panel (`?sim`). Build + lint OK |
| Brand / copy | app name only in `config/brand.json` (both apps). Mobile UI copy in `frontend/mobile/src/config/strings.ts` |
| Tooling | ✅ SDK, adb, `android` CLI, JDK 17 toolchain, Ninja swap, Python 3.13 venv, A54 authorized |

## How to see it

```bash
cd backend && .venv/Scripts/python.exe run.py                 # backend :8000
cd frontend/mobile && npm start                               # Metro; app already installed on the A54 (dev build)
adb reverse tcp:8000 tcp:8000 && adb reverse tcp:8081 tcp:8081
cd frontend/dashboard && npm run dev                          # http://localhost:5173 (?sim for the simulator panel)
backend/.venv/Scripts/python.exe notebooks/safety_client.py --interval 0.5   # or tools/sim.py for exact states
```

## Next up (in priority order; take one, move it to *In progress* with your name)

1. **Background/locked alerts on the device:** grant notifications (Settings → Phone setup → Allow), then verify that the foreground service keeps
   the socket alive with the screen off, that the full-screen intent wakes the A54 on `emergency`, and the alarm-channel sound in vibrate mode.
   Log the results in `android-alerting.md` → To verify.
2. **First-run onboarding:** profile + permissions walkthrough (notifications, battery Unrestricted), so a fresh phone is demo-ready in 1 minute.
3. **Release APK** (`npm run android:release`) on the A54, then the demo-phone prep checklist.
4. **Team alignment:** proposals in `contract-notes.md`: phone GPS speed → backend, dashboard sim panel posting `/telemetry`, SMS on emergency.
   Check what the Postgres/MinIO work changes in `docs/API.md` (trips may survive restarts; images in MinIO?).
5. **Polish:** landscape layout for a dash mount, app icon/splash, haptic patterns per level, a trip timeline/score chart on the summary.
6. Stretch: SYSTEM_ALERT_WINDOW bring-to-front during phone use, weekly stats / streaks, driver leaderboard (analytics endpoint).

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
- Trips live in backend memory until the DB lands. After a backend restart, old trip ids give 404.

## Open questions

- **Speed:** proposal: phone GPS through the backend (`expo-location` is ready). Needs a backend endpoint/message.
- **CV:** are `looking_behind` / `turning_around` separate outputs? Does `hands_off_wheel` mean both hands or at least one?
- **Emergency contact:** the app offers Text/Call buttons on the emergency screen. Should the backend send SMS itself?
- **Dashboard sim panel** posting `/telemetry` during demos: OK with the backend owner?
- **DB work:** will trips get user accounts (real login), or stay keyed by `driver_id`? (Profile is a local stand-in.)

## Manual steps only a human can do

- [x] Authorize USB debugging on the A54 · [x] Allow Python through the firewall
- [ ] On the A54: Settings tab → Phone setup → **Notifications: Allow**, **Unrestricted battery: Allow**, **DND: Open → allow**
- [ ] Android Studio install: when asked for the SDK location, choose the existing `%LOCALAPPDATA%\Android\Sdk`
- [ ] Docker Desktop + WSL (for the teammate's Postgres/MinIO). The new `vEthernet (WSL)` adapter is fine, because `run.py` picks the default-route IP
- [ ] Optional (admin): remove the `node.exe` Block firewall rules (`networking.md`)

## Session log

- 2026-11-06, session 1: toolchain setup (Android SDK + `android` CLI, JDK 17 toolchain, Python 3.13, Ninja long-path fix), Expo SDK 58
  scaffold with all native modules, web starter imported, `.claude/` knowledge base. The backend landed (`903df76`), so the docs were realigned
  to `docs/API.md`. The dev build was verified on the A54.
- 2026-11-06, session 2: mobile app core (API client, stores, alert engine, overlays, 6 screens) verified on the A54 with the real
  backend via `tools/sim.py`: warning flash + beeps, emergency siren screen, I'm OK, trip end → summary. Web car-screen dashboard
  built by a sub-agent (verified in Chrome on its own backend). `config/brand.json` is the single app-name source.
