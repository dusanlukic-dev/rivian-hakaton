# PROGRESS

> Live status board for humans and agents. **Read it first, update it last** (`.claude/rules/progress.md`).
> Keep it short and link to files. Details belong in `.claude/knowledge/`.
> Last updated: 2026-11-06, setup session (Claude, for Matija).

## Snapshot

| area | state |
|---|---|
| Backend (FastAPI) | **not in the repo yet** (teammate). Planned WS `ws://<ip>:8000/api/v1/ws` per their agent |
| CV models | manual / not integrated, so **mock everything** |
| Contract | **DRAFT v0** in `.claude/knowledge/ws-protocol.md`. Needs backend confirmation |
| Mobile app | Expo SDK 58 scaffold, clean `src/app` (placeholder screen), **all planned native modules installed and configured**. Dev build: BUILD_STATUS |
| Dashboard | user's starter copied to `frontend/dashboard`, deps installed, `npm run build` ✅. Not adapted to the project yet |
| Tooling (Matija's PC) | Android SDK + adb + Android CLI + portable JDK 17 toolchain installed. A54 authorized over USB ✅ |
| Shared docs | `.claude/` (CLAUDE.md, rules, skills, knowledge books), this file, README ✅ |

## What exists

- `frontend/mobile/app.json`: package `dev.hakaton.driveralert`, dark UI, permissions (notifications, full-screen intent, overlay,
  DND, battery-opt request), `RECORD_AUDIO` blocked, plugins: build-properties (cleartext, arm64-only), expo-audio (no mic),
  expo-camera (QR, no mic), expo-location (no background), expo-notifications (3 custom sounds), notify-kit (FGS `location`+`specialUse`,
  small icon `ic_stat_alert`), `plugins/withLockScreenActivity.js` (showWhenLocked + turnScreenOn).
- Native modules: expo-dev-client, react-native-notify-kit, expo-notifications, expo-audio, expo-speech, expo-keep-awake, expo-brightness,
  expo-navigation-bar, expo-network, expo-camera, expo-location, expo-intent-launcher, @react-native-async-storage/async-storage.
- `tools/gen-sounds.mjs` → `chime`, `alarm_warning`, `alarm_critical` WAVs in `frontend/mobile/assets/sounds` + `frontend/dashboard/public/sounds`.
- `frontend/dashboard`: Vite 8 + React 19 + Tailwind v4 + shadcn + Hugeicons starter with showcase (`/usage-examples`). `.env` → `http://localhost:8000`,
  and the `/api` proxy now forwards WebSockets.

## Next up (in priority order; take one, mark it *In progress* with your name)

1. **Mock server** `tools/mock-server/` (Node + `ws`) on `:8000`: `GET /api/v1/health`, `WS /api/v1/ws` emitting `state` at 10 Hz,
   scenarios from `metrics-and-scoring.md`, accepts `sim`/`hello`/`ping`/`ack`. This unblocks both apps.
2. **Mobile core:** `src/protocol/` (types, normalize, fallback), `src/connection/useCarSocket`, `src/settings/` (host/port/path +
   AsyncStorage + Test button), screens: Drive (live metrics, level, red pulse overlay, expo-audio alarm, vibration, keep-awake) and Settings.
3. **Mobile alerts:** create alarm-usage channels (expo-notifications), notify-kit notifications + "I'm focused" action, Drive-mode
   foreground service, full-screen intent, then run through the "To verify" list in `android-alerting.md`.
4. **Dashboard:** replace SignalR with `useCarSocket`, car-screen UI (metric icons, speed, level), red pulse + "Arm sound", sim panel
   (scenario buttons + sliders → `sim`), QR code of the WS URL.
5. **Backend alignment:** send `ws-protocol.md` to the backend teammate and settle the Open questions below. Then adapt `normalize.ts`.
6. **Demo hardening:** release APK on the A54, demo-phone prep (adb grants, battery Unrestricted), firewall rule, rehearsal script.
7. Stretch: phone GPS speed → `telemetry`; SYSTEM_ALERT_WINDOW bring-to-front; QR connect; LAN scan; app icon/branding; TTS lines.

## In progress

- (nothing)

## Known issues / risks

- **Windows firewall:** the hotspot network is *Public*, so the phone can't reach `laptop:8000` (or Metro over Wi-Fi) until an admin
  adds a rule or switches the profile to Private. See `.claude/knowledge/networking.md`. USB + `adb reverse` works regardless.
- New env vars (`ANDROID_HOME`, PATH → adb/android) only reach **newly started** shells. Restart VS Code once.
- Unverified: the sound-name format for the expo-notifications channel versus notify-kit; whether full-screen intent wakes the
  A54 (Android 16 needs the special-access toggle); FGS survival with the screen off on battery (Samsung kills it unless Unrestricted).
- `npm audit` reports moderate vulns in Expo/ESLint transitive deps. Ignored for the hackathon.
- The dashboard's main chunk is > 500 kB (inherited from the starter). Fine for a local demo.
- Python 3.15 on this laptop may be too new for backend wheels if the backend runs here. 3.12/3.13 is safer.

## Open questions

- **Backend:** the real message shape versus the `state` draft? Tick rate? Health endpoint? Does `run.py` bind `0.0.0.0`? Are client
  messages read? Who simulates the vehicle data (backend, or the dashboard sim panel through `sim`)?
- **CV team:** per-model output rate and format? `hands_on_wheel` as a count or a probability? Do they stream live, or replay clips?
- **Team:** app name/branding (placeholder "Driver Alert")? UI language (default English)? Will the phone be mounted (landscape) or handheld?

## Manual steps only a human can do

- [x] Authorize USB debugging on the A54 (2026-11-06)
- [ ] Firewall: run the elevated PowerShell lines in `.claude/knowledge/networking.md` § Windows gotchas
- [ ] Restart VS Code (env vars)
- [ ] After installing the app on the A54: Settings → Apps → Driver Alert → Battery → **Unrestricted**

## Session log

- 2026-11-06, Claude (setup for Matija): installed the Android SDK (cmdline-tools 23 with the new `android` CLI, platform-tools 37.0.1,
  platform 37.0, build-tools 37.0.0, NDK 27.1, CMake 3.30.5) and a portable JDK 17 Gradle toolchain, and set `ANDROID_HOME` + PATH.
  Scaffolded the Expo SDK 58 app with all planned native modules and alerting config. Copied the web starter into `frontend/dashboard`.
  Wrote `.claude/` (CLAUDE.md, rules, skills: android-device, mobile-dev, dashboard-dev, ship; knowledge: architecture, decisions,
  ws-protocol, metrics-and-scoring, android-alerting, networking, environment), README, and this file.
