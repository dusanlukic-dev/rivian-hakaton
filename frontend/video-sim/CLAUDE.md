# Video sim (a web "camera"): notes for Claude

Vite + React 19 + TS + Tailwind v4 page that sends a recorded clip to the backend's camera socket in real time.
Design and plan: `docs/2026-11-07-video-sim-design.md`, `docs/2026-11-07-video-sim-plan.md`. User docs: `README.md`.
Run every command from `frontend/video-sim/`.

## Commands

```bash
npm run dev      # http://localhost:5174; /api (incl. the camera WebSocket) proxied to VITE_API_URL (.env)
npm test         # Vitest in Node
npm run build    # tsc -b && vite build
npm run lint
```

## Map of src/

| Path | What |
|---|---|
| `config.ts` | FPS 10, MAX_WIDTH 1280, JPEG 0.8 (fallback 0.5), clips ≤ 120 s, 2 MB frame limit, 1 MB socket buffer limit, progress every 250 ms, driver `video-sim` |
| `strings.ts` | every user-facing string (English) |
| `lib/frames.ts` | `frameTimes`, `fitSize`, `durationError` (pure) and `extractFrames` (DOM: plays the clip at 4×, grabs frames with `requestVideoFrameCallback`) |
| `lib/schedule.ts` | `startSchedule`: frame i at t0 + i / fps; a late wake-up jumps to the newest due frame |
| `lib/senderCore.ts` | `runSender`: socket + schedule + skip while `bufferedAmount` is high; `progress` / `done` / `error`; worker message types |
| `lib/sender.worker.ts`, `lib/sender.ts` | the worker shell (real WebSocket, `performance.now`) and the page side (`startSending`) |
| `lib/backend.ts` | `apiBase`, `cameraSocketUrl`, `getStatus`, `startTrip`, `ensureTrip` |
| `lib/controller.ts` | the page flow (empty → preparing → ready → starting → sending); numbered runs drop stale callbacks |
| `useVideoSim.ts`, `App.tsx` | the controller wired to React (`useSyncExternalStore`) and the page |
| `test/fakeClock.ts` | test clock (`advance`, `jumpTo`) |

## Rules

- The backend doesn't change for this app. It uses only what a real camera and the phone use: `WS /api/v1/camera/ws`,
  `GET /api/v1/coordinator/status`, `POST /api/v1/trips` (only when no trip is active: it ends the one in progress).
- Never send faster than real time: the backend's timing (model clock, behaviour durations, sections) is frame arrival.
- Sending lives in the worker on purpose: a hidden tab throttles main-thread timers to 1/s.
- Strings only in `strings.ts`. Theme tokens only (copied from `../dashboard/src/index.css`), no hardcoded white or black.
- Tests run in Node, no jsdom. DOM code (`extractFrames`, the worker shell, the hook, `App`) has no unit tests: check
  it in a real browser.
- Imports: `@/…` → `src/`.

## Gotchas

- One seek per frame is slow: every seek decodes from the previous keyframe (minutes for sparse keyframes). That's why
  `extractFrames` plays the clip instead.
- `requestVideoFrameCallback` only runs for presented frames, so the extraction `<video>` sits on the page (2 px,
  nearly transparent), and the tab must be visible while preparing.
- WebM from MediaRecorder reports `duration = Infinity`: `extractFrames` seeks to 1e101 so the browser finds it.
- `controller.dispose()` must leave the controller usable: React StrictMode runs effect cleanups once on mount in dev.
- Vite only bundles the worker in this exact form: `new Worker(new URL('./sender.worker.ts', import.meta.url), { type: 'module' })`.
- Send stays on screen (disabled) while sending, so a double click can't land on Stop.
