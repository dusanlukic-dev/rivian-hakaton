# Architecture

**Personal Safety Reviewer.** An in-cabin camera watches the driver, the backend computes an **attention coefficient 0–100**, and the
car reacts: dashboard light, seat vibration, sound, and a message to an emergency contact. At the end of a trip the driver gets
statistics and tips. The company only ever sees coefficients and behaviour types, **never images**. Domain rules: root `CLAUDE.md`.
Contract: `docs/API.md`.

```
 laptop = car computer ─────────────────────────────────────────────────────────────────┐
 │ camera models (notebooks/, CV team)                                                   │
 │   detections → labels → SafetyClient ──POST 127.0.0.1:8000/api/v1/telemetry (~1/s)──┐ │
 │   (or simulators: notebooks/safety_client.py full drive · tools/sim.py exact states)│ │
 │                                                                                     ▼ │
 │ backend/ FastAPI (python run.py → 0.0.0.0:8000)                                       │
 │   scoring.py: score 0–100 · alerts.py: level → response (light, vibrate, sound, msg)  │
 │   in-memory trips · WS hub broadcast {type, data}                                     │
 │        │ ws://localhost:8000/api/v1/ws                  ▲ REST /trips (start/end)      │
 │        ▼                                                │                             │
 │ frontend/dashboard (browser) = car screen mock: lamp, score, behaviour icons,         │
 │   seat-vibration icon, sounds, QR for the phone, sim panel → POST /telemetry (proposal)│
 └────────┬──────────────────────────────────────────────────────────────────────────────┘
          │ phone's mobile hotspot (laptop IP printed by run.py, changes every session) or USB + adb reverse
          ▼
 Galaxy A54: frontend/mobile (Expo dev build)
   Settings (address, Test → GET /health, QR scan) · Profile (driver id, emergency contact)
   Drive: Start trip (POST /trips) → live lamp/score/behaviours (WS) + alerts (flash, sound, vibration, voice,
   emergency screen, foreground service, full-screen notification) → End (POST /trips/{id}/end) → Summary · History
```

## Ownership

| part | owner | status (see PROGRESS.md) |
|---|---|---|
| `notebooks/` CV models | CV team | manual and slow. `safety_client.py` is the bridge + simulator |
| `backend/`, `docs/API.md`, root `CLAUDE.md` | backend teammate Matija Vujić (`vujicmatija04@gmail.com`) | working, 27 tests (commit `903df76`). Adding Postgres + MinIO |
| repo / initial structure | `dusanlukic-dev` (GitHub owner) | |
| `frontend/mobile`, `frontend/dashboard`, `.claude/`, `PROGRESS.md`, `tools/`, `config/` | Matija Radović + agents | mobile core works on the A54 |

## Mobile app layout (`frontend/mobile`, implemented and verified on the A54 2026-11-06)

```
index.js                 entry: registers notify-kit foreground-service runner + background "I'm OK" action, then expo-router
app.config.ts            reads repo-root config/brand.json → app name + extra.brand (single source of the name)
src/api/                 types.ts (verbatim API.md §4) · client.ts (REST, ApiError, timeouts) · live.ts (WS, reconnect, kick) · address.ts
src/lib/                 store.ts (createStore/useStore on useSyncExternalStore) · persist.ts (AsyncStorage) · format.ts
src/state/               settings.ts (address, alert toggles) · profile.ts (local "account") · live.ts (socket status, active trip,
                         tick counter, emergency, last summary, local test alerts)
src/alerts/              engine.ts executes `response` per message: vibration, chime/alarm, voice, background notifications;
                         emergency: siren loop + vibration + max brightness + full-screen notification · sounds.ts (expo-audio)
                         · notifications.ts (channels, foreground service, permissions, settings deep links)
src/components/          ui.tsx (Txt, Screen, Card, Button, TextField, ToggleRow, Pill, Banner, Icon) · dashboard.tsx (Lamp,
                         LevelBar, BehaviorGrid, Indicators, StatusPill, ScoreBadge) · AlertOverlays.tsx (global 2 Hz red flash + emergency screen)
src/config/              strings.ts (ALL UI copy) · brand.ts · behaviors.ts (label → icon)
src/app/                 (tabs)/index (Drive) · history · profile · settings · trip/[id] (summary) · scan (QR)
```

**Rules:** only `src/api/` knows the wire format, and the UI tolerates unknown behaviour labels. Alerts are global (root layout), so they
show on every tab. The web dashboard mirrors the same `api/` shape.
