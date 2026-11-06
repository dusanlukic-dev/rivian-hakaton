# Rivian hackathon: driver-attention alerts

**Read `PROGRESS.md` (repo root) first.** It's the live status board: what exists, what's broken, what's next, and open questions.
Update it before you finish any task (`.claude/rules/progress.md`).

## What we're building

In-cabin camera → several small CV models (phone use, turned around, hands on wheel, drowsiness, eyes off road) → the FastAPI
backend fuses them with simulated vehicle data (speed, GPS speed) into a risk score → pushes it in real time over a WebSocket → the
driver's **phone app** (red pulse, high-pitch alarm, vibration, notifications, wakes the phone) and a **web dashboard** (mock car
screen) warn the driver during hands-on assisted driving. The laptop plays the car's computer, and the phone's mobile hotspot is
the in-car network. Diagram: `.claude/knowledge/architecture.md`.

## Repo map

| path | what | owner |
|---|---|---|
| `backend/` | FastAPI: fusion + WebSocket `ws://<ip>:8000/api/v1/ws` | teammate `dusanlukic-dev`; ask before editing |
| `frontend/mobile/` | Expo SDK 58 / RN 0.88 **dev build** for the driver's phone | us |
| `frontend/dashboard/` | Vite 8 + React 19 + Tailwind v4 + shadcn mock car screen + sim panel | us |
| `notebooks/` | CV/ML notebooks | CV team |
| `tools/` | repo scripts: `gen-sounds.mjs` (alert WAVs for both apps); `mock-server/` (planned) | us |
| `.claude/knowledge/` | knowledge books (below) | everyone |
| `.claude/rules/` | auto-loaded rules: `git`, `progress` always; `mobile`, `dashboard` when touching those folders | |
| `.claude/skills/` | reusable workflows (below) | |

## Knowledge books (read the relevant one before working in an area)

- `architecture.md`: system diagram, data flow, ownership, planned frontend module layout
- `decisions.md`: decision log D1…Dn (why Expo, why notify-kit, alarm stream, CNG…). Append when you decide something
- `ws-protocol.md`: **DRAFT** WebSocket contract with the backend. Diff it against the real backend when that lands
- `metrics-and-scoring.md`: CV signals, vehicle params, reference scoring (noisy-OR), alert levels → effects, mock scenarios
- `android-alerting.md`: how the phone sounds, flashes, vibrates and wakes; permissions; Samsung battery quirks; adb prep
- `networking.md`: hotspot topology, ports, finding the laptop IP, adb reverse, Windows firewall, cleartext
- `environment.md`: this PC's toolchain (Android SDK, JDK 17 toolchain + JDK 25, env vars, device facts)

## Skills

- `android-device`: adb + Android CLI. Connect/authorize, reverse ports, logs, **screenshots/layout tree for visual checks**, sleep/wake tests, permission prep
- `mobile-dev`: hot reload vs rebuild, prebuild, debug/release builds, toolchain, common errors
- `dashboard-dev`: dev server/proxy, build/lint, headless-Chrome screenshots
- `ship`: verify → update PROGRESS.md → commit (no AI attribution) → fetch/rebase → push to main

## Ground rules

- Git: commit and push to `main` freely. **Never add Co-Authored-By or any AI attribution.** See `.claude/rules/git.md`.
- `frontend/mobile/android/` is generated (CNG). Never hand-edit it; use `app.json` or config plugins.
- A native dependency or `app.json` change means a rebuild (`npm run android`). JS-only changes hot-reload.
- Both apps parse backend messages in exactly one adapter (`src/protocol/normalize.ts`) and must tolerate partial or unknown metrics.
- Contract changes: update `ws-protocol.md` and both adapters in the same commit.
- Flashing ≤ 3 Hz. Sound is the primary alert channel.
- When you learn something non-obvious, write it into the matching knowledge book. Turn repeated workflows into skills.
