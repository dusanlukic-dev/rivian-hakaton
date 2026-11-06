# Architecture

**Personal Safety Reviewer.** An in-cabin camera watches the driver, the backend computes an **attention coefficient 0–100**, and the
car reacts: dashboard light, seat vibration, sound, and a message to an emergency contact. At the end of a trip the driver gets
statistics and tips. The company only ever sees coefficients and behaviour types, **never images**. Domain rules: root `CLAUDE.md`.
Contract: `docs/API.md`.

```
 laptop = car computer ─────────────────────────────────────────────────────────────────┐
 │ camera models (notebooks/, CV team)                                                   │
 │   detections → labels → SafetyClient ──POST 127.0.0.1:8000/api/v1/telemetry (~1/s)──┐ │
 │   (or simulator: python notebooks/safety_client.py)                                 │ │
 │                                                                                     ▼ │
 │ backend/ FastAPI (python run.py → 0.0.0.0:8000)                                       │
 │   scoring.py: score 0–100 · alerts.py: level → response (light, vibrate, sound, msg)  │
 │   in-memory trips · WS hub broadcast {type, data}                                     │
 │        │ ws://localhost:8000/api/v1/ws                  ▲ REST /trips (start/end)      │
 │        ▼                                                │                             │
 │ frontend/dashboard (browser) = car screen mock: lamp, score, behaviour icons,         │
 │   seat-vibration icon, sounds, (proposal) sim panel → POST /telemetry                  │
 └────────┬──────────────────────────────────────────────────────────────────────────────┘
          │ phone's mobile hotspot (laptop IP printed by run.py, changes every session)
          ▼
 Galaxy A54: frontend/mobile (Expo dev build)
   Settings (IP + GET /health) → Start trip (driver id, emergency contact; POST /trips)
   → Drive (WS live: lamp colour, score, chips, vibration/sound per message, red pulse, keep-awake,
     foreground service + full-screen intent when locked) → End (POST /trips/{id}/end) → Summary; History
```

## Ownership

| part | owner | status (see PROGRESS.md) |
|---|---|---|
| `notebooks/` CV models | CV team | manual and slow. `safety_client.py` is the bridge + simulator |
| `backend/`, `docs/API.md`, root `CLAUDE.md` | backend teammate Matija Vujić (`vujicmatija04@gmail.com`) | working, 27 tests (commit `903df76`) |
| repo / initial structure | `dusanlukic-dev` (GitHub owner) | |
| `frontend/mobile`, `frontend/dashboard`, `.claude/`, `PROGRESS.md` | Matija Radović + agents | scaffolded |

## Frontend module layout (planned, the same shape in both apps)

```
src/api/types.ts      verbatim copy of docs/API.md §4 (keep identical in both apps)
src/api/client.ts     REST: health, startTrip, endTrip, getSummary, listTrips (base URL from settings)
src/api/live.ts       connectLive(): WebSocket with never-give-up reconnect (API.md §6 pattern) + "no data" watchdog during trips
src/alerts/           maps each TripState.response / emergency → effects (sound, vibration, flash, notification, TTS)
src/settings/         server host:port store (AsyncStorage on mobile, localStorage on web) + "Test connection"
```

**Rule:** only `src/api/` knows the wire format. The UI works with the typed objects and must tolerate unknown behaviour labels.
