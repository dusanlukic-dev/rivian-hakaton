# Architecture

**Personal Safety Reviewer.** An in-cabin camera watches the driver, the backend computes an **attention coefficient 0–100**, and the
car reacts: dashboard light, seat vibration, sound, and a message to an emergency contact. At the end of a trip the driver gets
statistics, tips and a **drive chart** (score over time, dangerous parts shaded, a picture of the worst moments). The company only
ever sees coefficients and behaviour types, **never images**. Domain rules: root `CLAUDE.md`. Contract: `docs/API.md`.
The backend split (coordinator / server / model) is explained in full in **`docs/ARCHITECTURE.md`** (Serbian); this is the summary.

```
 laptop = car computer ─────────────────────────────────────────────────────────────────────────────┐
 │ tools/camera_stream.py (test pattern / clip / webcam) ──JPEG per WS message──► /api/v1/camera/ws   │
 │ model/worker.py (own venv; CV detectors imported unchanged) ◄──frames── /api/v1/model/ws ──evidence──►│
 │ notebooks/safety_client.py, tools/sim.py (simulators) ──POST /api/v1/telemetry──────────────────────►│
 │                                                                                                    │
 │ backend/ (python run.py → 0.0.0.0:8000, one process, two parts)                                     │
 │   COORDINATOR app/coordinator: video cache (5 min, diskcache) · ModelLink · RiskEngine (CV copy)      │
 │     → scoring.py/alerts.py (score, level, response) → WS state ~2/s, emergency                      │
 │     → SectionRecorder: every 2 s a section (+ image of the riskiest frame if dangerous)             │
 │         → WS `section` · ServerOutbox ──POST /internal/trips/{id}/sync (in-process HTTP)──┐         │
 │   SERVER app/server: Postgres :5433 (trips, trip_sections) + RustFS :9000 (images) ◄─────┘         │
 │     → /auth, GET /trips, /trips/{id}/summary|report|sections, /media, /analytics                   │
 │        │ ws://localhost:8000/api/v1/ws                    ▲ REST                                   │
 │        ▼                                                  │                                        │
 │ frontend/dashboard (browser) = car screen mock: lamp, score, behaviour icons, seat/sound,           │
 │   QR for the phone, sim panel, end-of-trip summary + drive chart                                   │
 └────────┬───────────────────────────────────────────────────────────────────────────────────────────┘
          │ phone's hotspot (laptop IP printed by run.py) or USB + adb reverse
          ▼
 Galaxy A54: frontend/mobile (Expo dev build)
   Settings (address, Test, QR, alert toggles, test alerts, phone setup) · Profile
   Drive: Start (POST /trips) → lamp/score/behaviours + "last minute" strip from `section` (WS) + alerts → End → Summary
   Summary: stats + drive chart (sections, moments, image boxes) from GET /trips/{id}/report · History
```

## Ownership

| part | owner | status (see PROGRESS.md) |
|---|---|---|
| `notebooks/` CV models | CV team (ttcpavle, Djolekapppp) | `risk_pipeline.py` is imported by the worker, **never edited by us** |
| `model/` worker, `tools/camera_stream.py` | us (2026-11-06 evening) | fake mode verified end to end; real mode written, not run here (no models/dataset on this laptop) |
| `backend/`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, root `CLAUDE.md` | backend teammate Matija Vujić **and us** since the user asked us to work on the backend | coordinator/server split done, 81 tests |
| repo / initial structure | `dusanlukic-dev` (GitHub owner) | |
| `frontend/mobile`, `frontend/dashboard`, `.claude/`, `PROGRESS.md`, `config/` | Matija Radović + agents | report chart added |

## Mobile app layout (`frontend/mobile`)

```
index.js                 entry: registers notify-kit foreground-service runner + background "I'm OK" action, then expo-router
app.config.ts            reads repo-root config/brand.json → app name + extra.brand (single source of the name)
src/api/                 types.ts (verbatim API.md §4) · client.ts (REST + auth; Bearer token on every call, 401 → logout)
                         · live.ts (WS, reconnect, kick) · address.ts
src/lib/                 store.ts (createStore/useStore on useSyncExternalStore) · persist.ts (AsyncStorage) · format.ts
src/app-init.ts          boot check (D37): storage → live socket → session check (GET /auth/me ≤ 2.5 s) + first link answer
                         (≤ 1.5 s), cap 4 s, then `auth.ready` → the root layout hides the native splash. Offline: keeps the
                         saved session and re-checks once the car answers
src/state/               settings.ts · auth.ts (token + user, AsyncStorage `auth.v1`; `ready`, `verified`) · live.ts (socket
                         `status`, steady `link` checking/online/offline, active trip, tick, emergency, last summary, `preview` =
                         local test alert, `sections` = last 30 WS sections; on reconnect it drops a trip the car no longer runs)
                         · permissions.ts (re-check on foreground; re-submits the alarm channel once DND access appears)
src/alerts/              engine.ts executes `response` per message (vibration, sounds, voice, background notifications, emergency)
                         · sounds.ts (expo-audio) · notifications.ts (channels, foreground service, app-specific settings intents,
                         permission state incl. DND from modules/system-access)
src/components/          ui.tsx (the UI kit: Screen = keyboard-aware scroll + safe-area edges, Button sm/md/lg, TextField with
                         error/optional/secure eye, ListRow, Divider, Banner with action, TextLink) · dashboard.tsx (Lamp,
                         LevelBar, BehaviorGrid, Indicators, StatusPill, ScoreBadge)
                         · AlertOverlays.tsx (2 Hz red flash only while state is fresh, emergency screen)
                         · report.tsx (DriveChart on react-native-svg, ChartLegend, MomentList, MomentSheet, RecentSections)
src/config/              strings.ts (ALL UI copy) · brand.ts · behaviors.ts (label → icon)
src/app/                 _layout (KeyboardProvider; Stack.Protected: token → app, none → login) · login (log in / create
                         account, no connection UI) · connection (car-computer address: Settings row, or "Change address"
                         when login can't reach the server) · (tabs)/_layout (tab bar without ripple/elevation)
                         · (tabs)/index (Drive) · history (my trips) · profile (account, logout) · settings · trip/[id] · scan (QR)
modules/system-access/   local Expo module (Kotlin): isDndAccessGranted() = NotificationManager.isNotificationPolicyAccessGranted
```

**Rules:** only `src/api/` knows the wire format, and the UI tolerates unknown behaviour labels and unknown WS message types. The
backend decides levels and danger; the app only colours them. Alerts are global (root layout), so they show on every tab.
