# Agent workflow layer: frontend, tooling, shared knowledge

This file **adds to** the root `CLAUDE.md` (the team's domain rules, written in Serbian by the backend teammate) and defers to
**`docs/API.md`**, the backend ↔ app contract and **source of truth**. Read them as one.
**Read `PROGRESS.md` first.** It's the live status board. Update it before you finish any task (`.claude/rules/progress.md`).

## In one paragraph

**Personal Safety Reviewer.** Camera models label risky behaviours (phone, looking behind, turning around, hands off the wheel, drowsy)
→ `POST /telemetry` ~1/s → the FastAPI backend computes an attention score 0–100 and the car's response (light, seat vibration,
sound, message) → pushes it over a WebSocket → the **phone app** (Expo, Android) and a **web dashboard** (car screen mock) react.
The laptop plays the car's computer, and the phone's hotspot is the in-car network. Diagram: `.claude/knowledge/architecture.md`.

## Repo map

| path | what | owner |
|---|---|---|
| `CLAUDE.md` (root) | domain rules, levels, cross-cutting change rules (Serbian) | backend teammate |
| `docs/API.md` | **contract**: routes, TS types, WS events, how to display state | backend teammate |
| `backend/` | FastAPI app + tests. `backend/CLAUDE.md` has its layers and gotchas | backend teammate. **Run it, don't edit it** |
| `notebooks/` | CV models; `safety_client.py` = models→backend bridge + **drive simulator** | CV team / backend |
| `frontend/mobile/` | Expo SDK 58 / RN 0.88 **dev build** for the driver's phone | us |
| `frontend/dashboard/` | Vite 8 + React 19 + Tailwind v4 + shadcn car-screen mock | us |
| `tools/` | `gen-sounds.mjs` (alert WAVs for both apps) | us |
| `.claude/knowledge/`, `.claude/rules/`, `.claude/skills/` | knowledge books, auto-loaded rules, workflows | everyone |

## Knowledge books (read the relevant one before working in an area)

- `architecture.md`: diagram, ownership, planned frontend module layout (`src/api/` is the only place that knows the wire format)
- `contract-notes.md`: what we **verified** about `docs/API.md`, the frontend implications, and proposals for the backend
- `metrics-and-scoring.md`: behaviour labels, score math, the levels → response table, **field → phone/dashboard effect table**, demo drive
- `android-alerting.md`: sound on the alarm stream, flash, vibration, waking the phone, foreground service, permissions, Samsung quirks
- `networking.md`: hotspot topology, ports, adb reverse, **Windows firewall state** (python allowed, node blocked on Public)
- `environment.md`: this PC's toolchain (Android SDK + `android` CLI, JDK 17 toolchain + JDK 25, Python 3.13 venv, phone facts)
- `cv-pipeline.md`: the cabin camera dataset and `notebooks/risk_pipeline.py`: driver is on the RIGHT, ROIs, head-pose baseline, look-down vs eyes-closed, YOLO/hands limits
- `decisions.md`: decision log D1…Dn. Append when you decide something (D15: API.md supersedes our early draft)

## Skills

- `backend-local`: run the backend + simulator, probe the WS, check that the phone can reach it
- `android-device`: adb + Android CLI: connect, reverse ports, logs, **screenshots/layout tree/taps for visual checks**, sleep/wake tests, permission prep
- `mobile-dev`: hot reload vs rebuild, prebuild (CNG), debug/release builds, toolchain, common errors
- `dashboard-dev`: dev server/proxy, build/lint, headless-Chrome screenshots
- `ship`: verify → update PROGRESS.md → commit (no AI attribution) → fetch/rebase → push to main

## Ground rules

- Git: commit and push to `main` freely. **Never add Co-Authored-By or any AI attribution** (`.claude/rules/git.md`).
- The frontend never invents endpoints or fields, and never computes levels. It shows `response`. Missing something? Raise it with the backend.
- `frontend/mobile/android/` is generated (CNG). Never hand-edit it; use `app.json` or config plugins. A native change means a rebuild.
- Team chat is in Serbian. Code, identifiers, API and UI labels are in English (root `CLAUDE.md`).
- Flashing ≤ 3 Hz. Sound is the primary alert channel.
- When you learn something non-obvious, write it into the matching knowledge book. Turn repeated workflows into skills.
