# PROGRESS

> Live status board for humans and agents. **Read it first, update it last** (`.claude/rules/progress.md`).
> Keep it short and link to files. Details belong in `.claude/knowledge/`. Domain rules: root `CLAUDE.md`. Contract: `docs/API.md`.
> Last updated: 2026-11-06, setup session (Claude, for Matija Radović).

## Snapshot

| area | state |
|---|---|
| Backend (FastAPI) | ✅ working (teammate Matija Vujić, commit `903df76`). 27 tests pass on this laptop (`backend/.venv`, Python 3.13) |
| Simulator | ✅ `notebooks/safety_client.py` drives a full trip through every level, verified over WS |
| CV models | manual / not integrated. The simulator stands in for them |
| Contract | ✅ `docs/API.md` (source of truth). Frontend notes and verification: `.claude/knowledge/contract-notes.md` |
| Mobile app | Expo SDK 58 scaffold, placeholder screen, **all planned native modules + alerting config**. Dev build on the A54: first build in progress (Windows path-limit fix applied, D18) |
| Dashboard | user's starter in `frontend/dashboard`, deps installed, `npm run build` ✅. Not adapted to the project yet |
| Phone ↔ laptop | ✅ the phone reaches the backend over the hotspot (`10.190.62.27:8000`) and over USB (`adb reverse`) |
| Tooling (Matija's PC) | ✅ Android SDK + adb + `android` CLI, portable JDK 17 toolchain, Ninja 1.13.2 swap, Python 3.13, A54 authorized |

## What exists (frontend side)

- `frontend/mobile/app.json`: "Safety Reviewer", package `dev.hakaton.driveralert`, dark UI, permissions (notifications, full-screen
  intent, overlay, DND, battery-opt request), `RECORD_AUDIO` blocked. Plugins: build-properties (cleartext, arm64-only), expo-audio (no mic),
  expo-camera (QR, no mic), expo-location (no background), expo-notifications (3 custom sounds), notify-kit (FGS `location`+`specialUse`,
  small icon `ic_stat_alert`), `plugins/withLockScreenActivity.js` (showWhenLocked + turnScreenOn).
- Native modules: expo-dev-client, react-native-notify-kit, expo-notifications, expo-audio, expo-speech, expo-keep-awake, expo-brightness,
  expo-navigation-bar, expo-network, expo-camera, expo-location, expo-intent-launcher, @react-native-async-storage/async-storage.
- `tools/gen-sounds.mjs` → `chime`, `alarm_warning`, `alarm_critical` WAVs in `frontend/mobile/assets/sounds` + `frontend/dashboard/public/sounds`.
- `frontend/dashboard`: Vite 8 + React 19 + Tailwind v4 + shadcn + Hugeicons starter (+ `/usage-examples` showcase). `.env` → `http://localhost:8000`,
  and the `/api` proxy forwards WebSockets.

## Next up (in priority order; take one, move it to *In progress* with your name)

1. **Mobile core (API.md §3–7):** `src/api/` (copy §4 types, REST client, `connectLive` reconnecting WS), settings store + **Settings**
   screen (address, Test → `GET /health`), **Start trip** (driver id + emergency contact → `POST /trips`), **Drive** (lamp colour, score,
   behaviour chips, `vibrate_seat` → vibration and `sound` → chime/alarm per message, red pulse on high, keep-awake), **End → Summary**, **History**.
   Develop against the real backend + simulator (skill `backend-local`).
2. **Mobile alerts:** alarm-usage channels (expo-notifications), notify-kit notifications, Drive-mode foreground service, full-screen
   intent on `emergency` / `sound: high`, emergency screen (+ SMS proposal). Then run the "To verify" list in `android-alerting.md`.
3. **Dashboard:** copy the types, add a `useLive` hook (drop SignalR), car-screen UI (lamp, gauge, behaviour icons, seat-vibration icon,
   message), "Arm sound" + sounds, QR code of the WS address, trip summary card.
4. **Team alignment:** take the proposals in `contract-notes.md` (phone GPS speed, dashboard sim panel → `POST /telemetry`, SMS on
   emergency) to the backend teammate. Settle the open questions below.
5. **Demo hardening:** release APK on the A54, demo-phone prep (adb grants, battery Unrestricted), a rehearsal script using the
   simulator, and a backup plan over USB/`adb reverse` if the hotspot misbehaves.
6. Stretch: SYSTEM_ALERT_WINDOW bring-to-front, TTS lines per level, app icon/branding, landscape layout for a dash mount.

## In progress

- (nothing)

## Known issues / risks

- **`node.exe` is blocked inbound on Public networks** (an earlier firewall prompt was denied). Metro over Wi-Fi and the dashboard opened from
  another device won't work over the hotspot. USB + `adb reverse` and `localhost` are fine. The fix (admin) is in `networking.md`.
- New env vars (`ANDROID_HOME`, PATH → adb/android) only reach **newly started** shells. Restart VS Code once.
- **Windows long paths:** the SDK CMake's Ninja was swapped to 1.13.2 (D18). Other PCs, or an SDK CMake reinstall, need the same swap, or the C++ build fails.
- Unverified: the sound-name format for expo-notifications channels versus notify-kit; whether a full-screen intent wakes the A54 (Android 16
  needs the special-access toggle); FGS survival with the screen off on battery (Samsung kills it unless Unrestricted).
- There's no WS heartbeat while no trip is active, so silence can't detect a dead socket then (`contract-notes.md`).
- `npm audit` reports moderate vulns in Expo/ESLint transitive deps (ignored for the hackathon). The dashboard's main chunk is > 500 kB (from the starter).

## Open questions

- **Speed:** the camera doesn't know it. The models currently send a fixed value. Proposal: phone GPS through the backend (`expo-location` is ready). Needs a backend endpoint/message.
- **CV:** are `looking_behind` and `turning_around` separate model outputs? Does `hands_off_wheel` mean both hands or at least one?
- **Emergency contact:** the backend only logs. Should the app send the SMS (`Linking sms:`)?
- **Dashboard sim panel** posting to `POST /telemetry` during demos: OK with the backend owner?
- **Team:** phone mounted (landscape) or handheld during the demo? Fine to keep the app name "Safety Reviewer"?

## Manual steps only a human can do

- [x] Authorize USB debugging on the A54 (2026-11-06)
- [x] Allow Python through the Windows firewall on Public (prompt at the first `run.py`, 2026-11-06)
- [ ] Optional (admin): remove the `node.exe` Block rules, only needed for Metro over Wi-Fi / LAN dashboard (`networking.md`)
- [ ] Restart VS Code (env vars)
- [ ] After installing the app on the A54: Settings → Apps → Safety Reviewer → Battery → **Unrestricted**

## Session log

- 2026-11-06, Claude (setup for Matija Radović): installed the Android SDK (cmdline-tools 23 with the new `android` CLI, platform-tools 37.0.1,
  platform 37.0, build-tools 37.0.0, NDK 27.1, CMake 3.30.5 + Ninja 1.13.2), a portable JDK 17 Gradle toolchain and Python 3.13, and set
  `ANDROID_HOME` + PATH. Scaffolded the Expo SDK 58 app with all planned native modules and alerting config. Copied the web starter into
  `frontend/dashboard`. Wrote `.claude/` (rules, skills: backend-local, android-device, mobile-dev, dashboard-dev, ship; knowledge books).
- 2026-11-06, Claude: the backend landed mid-session (`903df76`), so the docs were realigned to `docs/API.md`. The speculative WS draft and
  mock-server plan were dropped (D15). Verified backend tests, the simulator → WS flow, and phone → backend over the hotspot and USB. Fixed the
  first native build (Windows path limit → Ninja swap, D18).
