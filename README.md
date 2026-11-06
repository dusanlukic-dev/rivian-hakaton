# Rivian hackathon: driver-attention alerts

In-cabin camera → small CV models (phone use, turned around, hands on wheel, drowsiness, eyes off road) → FastAPI fuses them with
vehicle data into a risk score → real-time WebSocket push → the **driver's phone** (red pulse, high-pitch alarm, vibration,
notifications, wakes the phone) and a **web dashboard** (mock car screen) warn the driver in hands-on assisted driving.

```
backend/              FastAPI fusion + WebSocket ws://<laptop-ip>:8000/api/v1/ws      (backend team)
frontend/mobile/      Expo SDK 58 / React Native 0.88 Android app (dev build)          (frontend)
frontend/dashboard/   Vite + React 19 + Tailwind + shadcn mock car screen + sim panel  (frontend)
notebooks/            CV / ML                                                          (CV team)
tools/                gen-sounds.mjs (alert sounds), mock-server/ (planned)
PROGRESS.md           live status board: start here
.claude/              agent rules, skills and knowledge books (architecture, WS protocol, scoring, Android alerting, networking)
```

## Quick start

**Dashboard**
```bash
cd frontend/dashboard
cp .env.example .env        # VITE_API_URL=http://localhost:8000
npm ci && npm run dev       # http://localhost:5173  (component docs: /usage-examples)
```

**Phone app** (Android, USB debugging on, `adb devices` shows the phone)
```bash
cd frontend/mobile
npm ci
npm run android             # builds + installs the dev build and starts Metro (first build takes a while)
npm run adb:reverse         # the phone's localhost:8000 then reaches the laptop over USB
```
Requirements: Node 20+, Android SDK (`ANDROID_HOME`), and a JDK 17 the Gradle toolchain can find. See `.claude/skills/mobile-dev/SKILL.md`
and `.claude/knowledge/environment.md`.

**Demo network:** the phone hosts a mobile hotspot, the laptop joins it, and the app connects to the laptop's IP
(`ipconfig` → WiFi IPv4). The Windows firewall must allow port 8000. See `.claude/knowledge/networking.md`.

## Contract

The WebSocket message format is a **draft** in `.claude/knowledge/ws-protocol.md`. Backend people: please confirm or correct it.
