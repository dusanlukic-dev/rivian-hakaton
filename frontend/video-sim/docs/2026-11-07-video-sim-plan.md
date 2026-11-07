# Video sim Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** sajt `frontend/video-sim/` koji izvuče JPEG frejmove iz klipa sa diska i pošalje ih u realnom vremenu (10/s) postojećem `WS /api/v1/camera/ws`, kao da je kamera.

**Architecture:** čista logika (vremena frejmova, raspored slanja, slanje, backend klijent, kontroler stranice) je u `src/lib/` i testira se u Node-u sa lažnim satom, socketom i fetch-om. Browser deo je tanak: `extractFrames` (`<video>` + canvas), Web Worker koji drži WS i tajmer, i React stranica nad kontrolerom (`useSyncExternalStore`).

**Tech Stack:** Vite 8, React 19, TypeScript 5.9, Tailwind v4, Vitest 5, ESLint 9 (isto kao `frontend/dashboard`).

**Spec:** `frontend/video-sim/docs/2026-11-07-video-sim-design.md`

## Global Constraints

- Sve novo je u `frontend/video-sim/`. Backend i ostali app-ovi se ne menjaju.
- Verzije kao u dashboardu: `vite ^8.3.5`, `@vitejs/plugin-react ^6.2.1`, `react`/`react-dom ^19.3.1`, `typescript ~5.9.3`, `tailwindcss`/`@tailwindcss/vite ^4.3.4`, `@fontsource-variable/ibm-plex-sans ^5.3.0`, `eslint`/`@eslint/js ^9.39.5`, `typescript-eslint ^8.72.1`, `eslint-plugin-react-hooks ^7.1.1`, `eslint-plugin-react-refresh ^0.5.7`, `globals ^17.14.0`, `@types/react`/`@types/react-dom ^19.3.0`, `@types/node ^24.19.2`, `vitest ^5.1.0`. Druge runtime zavisnosti nema.
- Backend (`main`, ne menja se): `GET /api/v1/coordinator/status` → `{ trip_id: string | null, … }`; `POST /api/v1/trips` sa `{ "driver_id": "video-sim" }` → 201 `{ trip_id, … }` i završava vožnju u toku; `WS /api/v1/camera/ws`: jedna binarna poruka = jedan JPEG ≤ 2 000 000 B.
- `src/config.ts`: `FPS = 10`, `MAX_WIDTH = 1280`, `JPEG_QUALITY = 0.8`, `FALLBACK_QUALITY = 0.5`, `MAX_DURATION_S = 120`, `MAX_FRAME_BYTES = 2_000_000`, `MAX_BUFFERED_BYTES = 1_000_000`, `PROGRESS_EVERY_MS = 250`, `DRIVER_ID = 'video-sim'`.
- Realno vreme: frejm `i` ide u `t0 + i × 1000 / FPS` ms, nikad brže. Zakasneli frejmovi se preskaču (najnoviji pobeđuje).
- Ceo tekst UI-ja je na engleskom i samo u `src/strings.ts` (tačan tekst u Task 1).
- Dev: port 5174, `/api` (sa `ws: true`) ide kroz Vite proxy na `VITE_API_URL` (podrazumevano `http://localhost:8000`). Build ide direktno na `VITE_API_URL`.
- Izgled: font IBM Plex Sans Variable i tokeni iz `frontend/dashboard/src/index.css`, tamna tema po `prefers-color-scheme`, bez zakucane bele ili crne.
- Importi preko `@/…` (→ `src/`), kao u dashboardu.
- Testovi: Vitest u Node okruženju (bez jsdom-a). DOM delovi (`extractFrames`, worker, hook, `App`) se proveravaju buildom i e2e proverom u Task 6.
- Git: ova sesija nema pristup root-u repoa (`.git`), pa koraka za commit nema. Veljko commituje `frontend/video-sim/` na kraju.
- Ova sesija: fajlovi se pišu u `/mnt/user-data/outputs/video-sim/`, testiraju tamo i kopiraju sa `device_commit_files` u `~/Desktop/rivian-hakaton/frontend/video-sim/`, gde se na kraju ponove `npm install`, testovi, build i lint.

## Review Focus

1. **Dupli klik na Send** (ili Send dok traje `starting`): tačno jedan `ensureTrip` i jedan worker. Drugi `POST /trips` bi završio prvu vožnju. → Task 5: `ignores a second send while starting`; Task 6 e2e S2.
2. **Novi fajl ili Stop usred pripreme, provere vožnje ili slanja:** staro izvlačenje se prekida, stari sender se gasi, a njegovi zakasneli događaji ne menjaju stranicu. → Task 5: `drops events from a superseded clip`, `stop while starting never starts the sender`, `choosing a file while sending stops the sender first`.
3. **WebM bez trajanja** (snimljen sa MediaRecorder-om, `duration = Infinity` dok se ne skenira): trajanje se izračuna i klip radi kao MP4. → Task 6 e2e S3.
4. **Tab nije vidljiv dok šalje** (bina): backend i dalje dobija oko 10 frejmova/s, pregled sme da stane. → Task 6 e2e S4 (glavna nit blokirana 3 s).
5. **Backend padne ili WS pukne usred slanja:** red sa greškom, stranica nazad na ready, Send radi čim se backend vrati. → Task 3: `reports a lost connection…`; Task 6 e2e S5.

---

### Task 1: Kostur app-a i matematika frejmova

**Files:**
- Create: `package.json`, `.gitignore`, `.env.example`, `index.html`, `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`, `eslint.config.js`
- Create: `src/main.tsx`, `src/App.tsx` (privremeno samo naslov), `src/index.css`, `src/config.ts`, `src/strings.ts`, `src/lib/frames.ts`
- Test: `src/lib/frames.test.ts`

**Interfaces:**
- Produces: konstante iz Global Constraints u `src/config.ts`; `strings` u `src/strings.ts`;
  `frameTimes(durationS: number, fps: number): number[]`, `fitSize(width: number, height: number, maxWidth: number): { width: number; height: number }`,
  `durationError(durationS: number): string | null`, `interface ExtractedClip { frames: ArrayBuffer[]; durationS: number; width: number; height: number }` u `src/lib/frames.ts`.

- [ ] **Step 1: Kostur.** `package.json` (name `video-sim`, `"type": "module"`, skripte `dev: vite`, `build: tsc -b && vite build`, `lint: eslint .`, `preview: vite preview`, `test: vitest run`, verzije iz Global Constraints). `tsconfig.*` i `eslint.config.js` kao u dashboardu, bez shadcn izuzetka. `vite.config.ts`: `/// <reference types="vitest/config" />`, `resolve.tsconfigPaths: true`, pluginovi `react()` i `tailwindcss()`, `worker.format: 'es'`, `server.port: 5174`, `server.proxy['/api'] = { target: VITE_API_URL || 'http://localhost:8000', ws: true, changeOrigin: true }` (iz `loadEnv`), `test: { environment: 'node', include: ['src/**/*.test.ts'] }`. `.env.example`: `VITE_API_URL=http://localhost:8000` sa komentarom kao u dashboardu. `.gitignore`: `node_modules`, `dist`, `.env`, `*.local`. `index.html` sa naslovom `Video sim`. `src/index.css`: `@import 'tailwindcss'`, font, tokeni `background, foreground, card, card-foreground, primary, primary-foreground, muted, muted-foreground, border, destructive, radius` prepisani iz dashboard `:root`, tamne vrednosti iz `.dark` u `@media (prefers-color-scheme: dark) { :root { … } }`, `@theme inline` mapiranje `--color-*` i `--font-sans`. Zatim `npm install`.

- [ ] **Step 2: Failing test** `src/lib/frames.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { strings } from '@/strings'
import { durationError, fitSize, frameTimes } from './frames'

describe('frameTimes', () => {
  it('gives floor(duration × fps) frames, 0.1 s apart at 10 fps', () => {
    const t = frameTimes(30, 10)
    expect(t).toHaveLength(300)
    expect(t[0]).toBe(0)
    expect(t[1]).toBeCloseTo(0.1)
    expect(t[299]).toBeCloseTo(29.9)
  })
  it('ignores a fraction of a frame at the end', () => expect(frameTimes(30.04, 10)).toHaveLength(300))
  it('always gives at least one frame', () => expect(frameTimes(0.05, 10)).toEqual([0]))
})

describe('fitSize', () => {
  it('scales a 1080p clip down to 1280×720', () => expect(fitSize(1920, 1080, 1280)).toEqual({ width: 1280, height: 720 }))
  it('never scales up', () => expect(fitSize(640, 480, 1280)).toEqual({ width: 640, height: 480 }))
  it('rounds to whole pixels', () => expect(fitSize(1001, 563, 1000)).toEqual({ width: 1000, height: 562 }))
})

describe('durationError', () => {
  it('accepts clips up to 2 minutes', () => {
    expect(durationError(30)).toBeNull()
    expect(durationError(120)).toBeNull()
  })
  it('rejects a longer clip', () => expect(durationError(120.5)).toBe(strings.errors.tooLong))
  it('rejects an unknown or empty duration', () => {
    for (const d of [Infinity, Number.NaN, 0]) expect(durationError(d)).toBe(strings.errors.cantDecode)
  })
})
```

- [ ] **Step 3: Run** `npm test`. Expected: FAIL (ne postoje `./frames` i `@/strings`).

- [ ] **Step 4: Implementiraj** `src/config.ts` (Global Constraints), `src/lib/frames.ts` (broj frejmova `max(1, floor(durationS × fps + 1e-6))`, `t_i = i / fps`; `fitSize` sa `Math.round`, bez uvećanja) i `src/strings.ts` sa tačno ovim tekstom:

```ts
export const strings = {
  title: 'Video sim',
  subtitle: 'Plays a recorded clip as the in-cabin camera: frames go to the backend in real time.',
  drop: 'Drop a video here or click to choose',
  preparing: (done: number, total: number) => `Preparing frames ${done} / ${total}`,
  clipInfo: (frames: number, seconds: number, width: number, height: number) =>
    `${frames} frames · ${seconds.toFixed(1)} s · ${width}×${height}`,
  send: 'Send',
  stop: 'Stop',
  chooseAnother: 'Choose another',
  checkingTrip: 'Checking trip…',
  progress: (sentS: number, totalS: number) => `${sentS.toFixed(1)} / ${totalS.toFixed(1)} s`,
  startedTrip: 'Started trip video-sim',
  activeTrip: 'Sending into the active trip',
  sentSummary: (sent: number, skipped: number) => `Sent ${sent} frames, ${skipped} skipped`,
  errors: {
    notVideo: 'That file is not a video.',
    cantDecode: "This browser can't decode the video. Export it as MP4 (H.264).",
    tooLong: 'The clip is longer than 2 minutes. Trim it first.',
    frameTooBig: 'A frame is still larger than 2 MB. Use a smaller video.',
    unreachable: (base: string) => `Backend not reachable at ${base}. Start it with python run.py.`,
    tripFailed: (detail: string) => `Couldn't start a trip: ${detail}`,
    lost: (seconds: number) => `Lost the connection to the backend after ${seconds.toFixed(1)} s.`,
    cantConnect: "Couldn't connect to the backend camera socket.",
    senderCrashed: 'The sender stopped unexpectedly.',
  },
}
```

`cantConnect` i `senderCrashed` su pojašnjenje speca: WS koji se nikad ne otvori nema „after X s“, a pad workera je greška bez WS-a.

- [ ] **Step 5: Run** `npm test`. Expected: PASS, 9 testova.
- [ ] **Step 6: Run** `npm run build && npm run lint`. Expected: build bez grešaka, lint bez grešaka i upozorenja.

---

### Task 2: Raspored u realnom vremenu

**Files:**
- Create: `src/lib/schedule.ts`, `src/test/fakeClock.ts`
- Test: `src/lib/schedule.test.ts`

**Interfaces:**
- Produces (`src/lib/schedule.ts`):
  ```ts
  export interface Clock { now(): number; setTimeout(fn: () => void, ms: number): unknown; clearTimeout(handle: unknown): void }
  export interface ScheduleOptions {
    count: number; fps: number; clock: Clock
    onFrame(index: number, skippedBefore: number): void  // frejm index je na redu; skippedBefore pre njega se preskače
    onDone(): void                                       // u t0 + count × 1000/fps
  }
  export function startSchedule(options: ScheduleOptions): () => void  // vraća stop
  ```
- Produces (`src/test/fakeClock.ts`): `class FakeClock implements Clock` sa poljem `t` (ms, kreće od 0), getterom `pending: number`, i metodama `advance(ms)` (pušta svaki tajmer koji dospe do `t + ms`, svaki u svom trenutku, pa `t = t + ms`) i `jumpTo(target)` (kasno buđenje: prvo `t = target`, pa pusti sve dospele tajmere sa `now() = target`).

- [ ] **Step 1: Failing test** `src/lib/schedule.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'
import { FakeClock } from '@/test/fakeClock'
import { startSchedule } from './schedule'

function run(count: number) {
  const clock = new FakeClock()
  const frames: [number, number][] = []
  const onDone = vi.fn()
  const stop = startSchedule({ count, fps: 10, clock, onFrame: (i, s) => void frames.push([i, s]), onDone })
  return { clock, frames, onDone, stop }
}

describe('startSchedule', () => {
  it('sends frame 0 at once, then one every 100 ms, and ends at count × 100 ms', () => {
    const { clock, frames, onDone } = run(3)
    expect(frames).toEqual([[0, 0]])
    clock.advance(100)
    clock.advance(100)
    expect(frames).toEqual([[0, 0], [1, 0], [2, 0]])
    expect(onDone).not.toHaveBeenCalled()
    clock.advance(100)
    expect(onDone).toHaveBeenCalledTimes(1)
    expect(clock.pending).toBe(0)
  })
  it('jumps to the newest due frame after a late wake-up', () => {
    const { clock, frames } = run(10)
    clock.jumpTo(350)
    expect(frames).toEqual([[0, 0], [3, 2]])
    clock.advance(50)
    expect(frames.at(-1)).toEqual([4, 0])
  })
  it('ends right away when the last wake-up comes after the clip end', () => {
    const { clock, frames, onDone } = run(3)
    clock.jumpTo(1000)
    expect(frames).toEqual([[0, 0], [2, 1]])
    expect(onDone).toHaveBeenCalledTimes(1)
  })
  it('stop() cancels everything', () => {
    const { clock, frames, onDone, stop } = run(5)
    stop()
    clock.advance(1000)
    expect(frames).toEqual([[0, 0]])
    expect(onDone).not.toHaveBeenCalled()
    expect(clock.pending).toBe(0)
  })
})
```

- [ ] **Step 2: Run** `npm test -- schedule`. Expected: FAIL (ne postoje moduli).
- [ ] **Step 3: Implementiraj** `FakeClock` i `startSchedule`. Algoritam pri svakom buđenju (prvo odmah u `startSchedule`), `interval = 1000 / fps`, `elapsed = now − t0`:
  `due = min(count, floor(elapsed / interval + 1e-9) + 1)`; ako je `due > next`: `onFrame(due − 1, due − 1 − next)`, `next = due`. Ako je `next === count`: `onDone()` u `count × interval` (odmah ako je prošlo). Inače sledeće buđenje u `next × interval`.
- [ ] **Step 4: Run** `npm test`. Expected: PASS (Task 1 + 4 nova).

---

### Task 3: Slanje kroz Web Worker

**Files:**
- Create: `src/lib/senderCore.ts`, `src/lib/sender.worker.ts`, `src/lib/sender.ts`
- Test: `src/lib/senderCore.test.ts`

**Interfaces:**
- Consumes: `Clock`, `startSchedule` (Task 2); `strings`, `MAX_BUFFERED_BYTES`, `PROGRESS_EVERY_MS` (Task 1).
- Produces (`src/lib/senderCore.ts`):
  ```ts
  export interface Transport { send(data: ArrayBuffer): void; bufferedAmount(): number; close(): void }
  export type Connect = (url: string, handlers: { onOpen(): void; onClose(): void }) => Transport
  export interface SendJob { url: string; frames: ArrayBuffer[]; fps: number }
  export type SenderEvent =
    | { type: 'progress'; index: number; sent: number; skipped: number }
    | { type: 'done'; sent: number; skipped: number }
    | { type: 'error'; message: string }
  export type WorkerRequest = ({ type: 'start' } & SendJob) | { type: 'stop' }
  export function runSender(
    job: SendJob,
    deps: { connect: Connect; clock: Clock; maxBufferedBytes: number; progressEveryMs: number },
    emit: (event: SenderEvent) => void,
  ): () => void  // vraća stop
  ```
- Produces (`src/lib/sender.ts`): `startSending(job: SendJob, onEvent: (event: SenderEvent) => void): () => void` (glavna nit; pokreće worker).

- [ ] **Step 1: Failing test** `src/lib/senderCore.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { strings } from '@/strings'
import { FakeClock } from '@/test/fakeClock'
import { runSender, type Connect, type SenderEvent } from './senderCore'

class FakeLink {
  url = ''
  sent: ArrayBuffer[] = []
  buffered = 0
  closed = false
  handlers: { onOpen(): void; onClose(): void } | null = null
  connect: Connect = (url, handlers) => {
    this.url = url
    this.handlers = handlers
    return { send: (d) => void this.sent.push(d), bufferedAmount: () => this.buffered, close: () => void (this.closed = true) }
  }
}

function setup(count: number) {
  const clock = new FakeClock()
  const link = new FakeLink()
  const events: SenderEvent[] = []
  const frames = Array.from({ length: count }, (_, i) => new Uint8Array([0xff, 0xd8, 0xff, i]).buffer)
  const stop = runSender(
    { url: 'ws://car/api/v1/camera/ws', frames, fps: 10 },
    { connect: link.connect, clock, maxBufferedBytes: 1_000_000, progressEveryMs: 250 },
    (e) => void events.push(e),
  )
  return { clock, link, events, frames, stop, open: () => link.handlers!.onOpen() }
}

describe('runSender', () => {
  it('connects to the url and sends nothing before the socket opens', () => {
    const { clock, link } = setup(3)
    clock.advance(1000)
    expect(link.url).toBe('ws://car/api/v1/camera/ws')
    expect(link.sent).toHaveLength(0)
  })
  it('sends every frame in real time once open, then reports done and closes', () => {
    const { clock, link, events, frames, open } = setup(3)
    open()
    expect(link.sent).toEqual([frames[0]])
    clock.advance(100)
    expect(link.sent).toEqual(frames.slice(0, 2))
    clock.advance(200)
    expect(link.sent).toEqual(frames)
    expect(events.at(-1)).toEqual({ type: 'done', sent: 3, skipped: 0 })
    expect(link.closed).toBe(true)
  })
  it('skips a frame while the socket still holds more than maxBufferedBytes', () => {
    const { clock, link, events, frames, open } = setup(3)
    open()
    link.buffered = 1_500_000
    clock.advance(100)
    link.buffered = 0
    clock.advance(200)
    expect(link.sent).toEqual([frames[0], frames[2]])
    expect(events.at(-1)).toEqual({ type: 'done', sent: 2, skipped: 1 })
  })
  it('reports progress at once and then at most every 250 ms', () => {
    const { clock, events, open } = setup(10)
    open()
    clock.advance(1000)
    expect(events.filter((e) => e.type === 'progress').map((e) => e.index)).toEqual([0, 3, 6, 9])
  })
  it('reports a lost connection with the seconds already sent and stops sending', () => {
    const { clock, link, events, open } = setup(10)
    open()
    clock.advance(100)
    link.handlers!.onClose()
    clock.advance(1000)
    expect(link.sent).toHaveLength(2)
    expect(events.at(-1)).toEqual({ type: 'error', message: strings.errors.lost(0.2) })
  })
  it('reports a socket that never opened', () => {
    const { link, events } = setup(3)
    link.handlers!.onClose()
    expect(events).toEqual([{ type: 'error', message: strings.errors.cantConnect }])
  })
  it('stop() closes the socket and reports nothing more', () => {
    const { clock, link, events, stop, open } = setup(10)
    open()
    const before = events.length
    stop()
    expect(link.closed).toBe(true)
    clock.advance(2000)
    link.handlers!.onClose()
    expect(link.sent).toHaveLength(1)
    expect(events).toHaveLength(before)
  })
})
```

- [ ] **Step 2: Run** `npm test -- senderCore`. Expected: FAIL (ne postoji `./senderCore`).
- [ ] **Step 3: Implementiraj `runSender`.** `connect` odmah. `onOpen` → `startSchedule`. Svaki frejm: `skipped += skippedBefore`; ako `bufferedAmount() > maxBufferedBytes` → `skipped += 1`, inače `send` i `sent += 1`; `progress` za indeks 0 i kad je prošlo ≥ `progressEveryMs` od prošlog. `onDone` → `done`, pa `close()`. `onClose` posle `done` ili `stop` se ignoriše; pre otvaranja → `cantConnect`, posle → `lost((poslednji indeks + 1) / fps)`, i raspored staje.
- [ ] **Step 4: Run** `npm test`. Expected: PASS (7 novih).
- [ ] **Step 5: Implementiraj `sender.worker.ts` i `sender.ts`.** Worker: `const scope = self as unknown as { onmessage: ((e: MessageEvent<WorkerRequest>) => void) | null; postMessage(event: SenderEvent): void }`; `start` gasi prethodni posao i pokreće `runSender` sa pravim `WebSocket`-om (`binaryType = 'arraybuffer'`, `onopen`/`onclose` → handlers, `bufferedAmount` čita sa socketa), satom `performance.now()` + `setTimeout`/`clearTimeout`, `MAX_BUFFERED_BYTES`, `PROGRESS_EVERY_MS`, `emit = scope.postMessage`; `stop` gasi posao. `startSending`: `new Worker(new URL('./sender.worker.ts', import.meta.url), { type: 'module' })`, poruke prosleđuje u `onEvent`, posle `done` ili `error` gasi worker (`terminate`), `onerror` → `{ type: 'error', message: strings.errors.senderCrashed }`; vraćeni stop šalje `{ type: 'stop' }` i gasi worker.
- [ ] **Step 6: Run** `npm run build && npm run lint`. Expected: oba prolaze, a `dist/assets/` ima zaseban `sender.worker-*.js`.

---

### Task 4: Backend klijent

**Files:**
- Create: `src/lib/backend.ts`
- Test: `src/lib/backend.test.ts`

**Interfaces:**
- Consumes: `strings`, `DRIVER_ID` (Task 1).
- Produces (`src/lib/backend.ts`):
  ```ts
  export const API_PREFIX = '/api/v1'
  export function apiBase(): string        // '' u dev-u (isti origin, Vite proxy), VITE_API_URL u buildu
  export function backendLabel(): string   // VITE_API_URL || 'http://localhost:8000', za poruke
  export function toWsUrl(httpBase: string): string  // http(s)://host[:port][/] → ws(s)://host[:port]/api/v1/camera/ws
  export function cameraSocketUrl(): string          // toWsUrl(apiBase() || location.origin)
  export interface CoordinatorStatus { trip_id: string | null }
  export function getStatus(): Promise<CoordinatorStatus>
  export function startTrip(): Promise<{ trip_id: string }>
  export interface TripApi { getStatus(): Promise<CoordinatorStatus>; startTrip(): Promise<{ trip_id: string }> }
  export function ensureTrip(api?: TripApi): Promise<{ tripId: string; started: boolean }>  // podrazumevano { getStatus, startTrip }
  ```

- [ ] **Step 1: Failing test** `src/lib/backend.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { strings } from '@/strings'
import { backendLabel, ensureTrip, getStatus, startTrip, toWsUrl } from './backend'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
afterEach(() => void vi.unstubAllGlobals())

describe('toWsUrl', () => {
  it('turns the http base into the camera socket url', () => {
    expect(toWsUrl('http://localhost:8000')).toBe('ws://localhost:8000/api/v1/camera/ws')
    expect(toWsUrl('https://abc.ngrok.app/')).toBe('wss://abc.ngrok.app/api/v1/camera/ws')
  })
})

describe('ensureTrip', () => {
  it('uses the active trip and starts none', async () => {
    const api = { getStatus: vi.fn().mockResolvedValue({ trip_id: 't1' }), startTrip: vi.fn() }
    await expect(ensureTrip(api)).resolves.toEqual({ tripId: 't1', started: false })
    expect(api.startTrip).not.toHaveBeenCalled()
  })
  it('starts a trip only when none is active', async () => {
    const api = { getStatus: vi.fn().mockResolvedValue({ trip_id: null }), startTrip: vi.fn().mockResolvedValue({ trip_id: 't2' }) }
    await expect(ensureTrip(api)).resolves.toEqual({ tripId: 't2', started: true })
    expect(api.startTrip).toHaveBeenCalledTimes(1)
  })
})

describe('getStatus', () => {
  it('reads /api/v1/coordinator/status', async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(200, { trip_id: null, camera: {} }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getStatus()).resolves.toMatchObject({ trip_id: null })
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/v1\/coordinator\/status$/)
  })
  it('says the backend is not reachable when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(getStatus()).rejects.toThrow(strings.errors.unreachable(backendLabel()))
  })
  it('says the same when the dev proxy answers 502', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 502 })))
    await expect(getStatus()).rejects.toThrow(strings.errors.unreachable(backendLabel()))
  })
})

describe('startTrip', () => {
  it('posts driver_id video-sim as JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(201, { trip_id: 't3' }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(startTrip()).resolves.toMatchObject({ trip_id: 't3' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/v1\/trips$/)
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({ 'content-type': 'application/json' })
    expect(JSON.parse(init.body)).toEqual({ driver_id: 'video-sim' })
  })
  it.each([
    [json(422, { detail: [{ msg: 'driver_id is required' }] }), 'driver_id is required'],
    [json(409, { detail: 'No active trip' }), 'No active trip'],
    [new Response('oops', { status: 500 }), 'HTTP 500'],
  ])('reports the backend detail (%#)', async (response, detail) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    await expect(startTrip()).rejects.toThrow(strings.errors.tripFailed(detail))
  })
  it('says the backend is not reachable when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(startTrip()).rejects.toThrow(strings.errors.unreachable(backendLabel()))
  })
})
```

- [ ] **Step 2: Run** `npm test -- backend`. Expected: FAIL (ne postoji `./backend`).
- [ ] **Step 3: Implementiraj `backend.ts`** po Interfaces. `detail` iz JSON tela: string, ili `detail[0].msg` za niz, inače `HTTP <status>`.
- [ ] **Step 4: Run** `npm test`. Expected: PASS (11 novih).

---

### Task 5: Kontroler stranice

**Files:**
- Create: `src/lib/controller.ts`
- Test: `src/lib/controller.test.ts`

**Interfaces:**
- Consumes: `ExtractedClip` (Task 1), `SendJob`, `SenderEvent` (Task 3), `strings` (Task 1).
- Produces (`src/lib/controller.ts`):
  ```ts
  export type Phase = 'empty' | 'preparing' | 'ready' | 'starting' | 'sending'
  export interface Clip { name: string; url: string; frames: ArrayBuffer[]; durationS: number; width: number; height: number }
  export interface SimState {
    phase: Phase
    clip: Clip | null                               // od preparing nadalje; frames [] dok nije ready
    prepared: { done: number; total: number } | null
    sentS: number                                   // (index + 1) / fps poslednjeg progress-a
    note: string | null
    error: string | null
  }
  export interface ControllerDeps {
    extract(file: File, onProgress: (done: number, total: number) => void, signal: AbortSignal): Promise<ExtractedClip>
    ensureTrip(): Promise<{ tripId: string; started: boolean }>
    startSending(job: Omit<SendJob, 'url'>, onEvent: (event: SenderEvent) => void): () => void
    objectUrl: { create(file: File): string; revoke(url: string): void }
    preview(): { play(): void; pause(): void } | null
    fps: number
  }
  export interface Controller {
    getState(): SimState                        // isti objekat dok se nešto ne promeni (useSyncExternalStore)
    subscribe(listener: () => void): () => void
    chooseFile(file: File): void
    send(): void                                // samo iz ready
    stop(): void                                // samo iz starting/sending
    dispose(): void                             // gasi sve i oslobađa url, ali kontroler ostaje upotrebljiv (StrictMode)
  }
  export function createController(deps: ControllerDeps): Controller
  ```

- [ ] **Step 1: Failing test** `src/lib/controller.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'
import { strings } from '@/strings'
import type { ExtractedClip } from './frames'
import type { SenderEvent } from './senderCore'
import { createController, type ControllerDeps } from './controller'

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)))
  return { promise, resolve, reject }
}
const flush = () => new Promise((r) => setTimeout(r, 0))
const clip = (n = 300): ExtractedClip => ({ frames: Array.from({ length: n }, () => new ArrayBuffer(4)), durationS: n / 10, width: 1280, height: 720 })
const file = (name = 'clip.mp4') => new File([new Uint8Array(1)], name, { type: 'video/mp4' })
type Trip = { tripId: string; started: boolean }

function setup() {
  const extractions: { onProgress: (d: number, t: number) => void; signal: AbortSignal; result: ReturnType<typeof deferred<ExtractedClip>> }[] = []
  const trips: ReturnType<typeof deferred<Trip>>[] = []
  const senders: { job: { frames: ArrayBuffer[]; fps: number }; emit: (e: SenderEvent) => void; stop: ReturnType<typeof vi.fn> }[] = []
  const preview = { play: vi.fn(), pause: vi.fn() }
  let urls = 0
  const deps: ControllerDeps = {
    extract: (_f, onProgress, signal) => {
      const result = deferred<ExtractedClip>()
      extractions.push({ onProgress, signal, result })
      return result.promise
    },
    ensureTrip: () => {
      const d = deferred<Trip>()
      trips.push(d)
      return d.promise
    },
    startSending: (job, emit) => {
      const stop = vi.fn()
      senders.push({ job, emit, stop })
      return stop
    },
    objectUrl: { create: () => `blob:${++urls}`, revoke: vi.fn() },
    preview: () => preview,
    fps: 10,
  }
  const controller = createController(deps)
  return { controller, deps, extractions, trips, senders, preview, state: () => controller.getState() }
}
type T = ReturnType<typeof setup>
async function ready(t: T, name = 'clip.mp4') {
  t.controller.chooseFile(file(name))
  t.extractions.at(-1)!.result.resolve(clip())
  await flush()
}
async function sending(t: T, started = true) {
  await ready(t)
  t.controller.send()
  t.trips.at(-1)!.resolve({ tripId: 't', started })
  await flush()
  t.senders.at(-1)!.emit({ type: 'progress', index: 0, sent: 1, skipped: 0 })
}

describe('controller', () => {
  it('prepares a chosen file and becomes ready', async () => {
    const t = setup()
    const listener = vi.fn()
    t.controller.subscribe(listener)
    t.controller.chooseFile(file())
    expect(t.state()).toMatchObject({ phase: 'preparing', clip: { name: 'clip.mp4', url: 'blob:1' }, error: null })
    t.extractions[0].onProgress(150, 300)
    expect(t.state().prepared).toEqual({ done: 150, total: 300 })
    t.extractions[0].result.resolve(clip())
    await flush()
    expect(t.state()).toMatchObject({ phase: 'ready', prepared: null, clip: { durationS: 30, width: 1280, height: 720 } })
    expect(t.state().clip!.frames).toHaveLength(300)
    expect(listener).toHaveBeenCalled()
  })
  it('shows an extraction error, goes back to empty and frees the url', async () => {
    const t = setup()
    t.controller.chooseFile(file())
    t.extractions[0].result.reject(new Error(strings.errors.tooLong))
    await flush()
    expect(t.state()).toMatchObject({ phase: 'empty', clip: null, error: strings.errors.tooLong })
    expect(t.deps.objectUrl.revoke).toHaveBeenCalledWith('blob:1')
  })
  it('drops events from a superseded clip', async () => {
    const t = setup()
    t.controller.chooseFile(file('a.mp4'))
    t.controller.chooseFile(file('b.mp4'))
    expect(t.extractions[0].signal.aborted).toBe(true)
    expect(t.deps.objectUrl.revoke).toHaveBeenCalledWith('blob:1')
    t.extractions[0].onProgress(10, 300)
    t.extractions[0].result.resolve(clip())
    await flush()
    expect(t.state()).toMatchObject({ phase: 'preparing', clip: { name: 'b.mp4' }, prepared: null })
    t.extractions[1].result.resolve(clip(50))
    await flush()
    expect(t.state()).toMatchObject({ phase: 'ready', clip: { name: 'b.mp4', durationS: 5 } })
  })
  it('sends: checks the trip, starts the sender, follows progress and ends ready', async () => {
    const t = setup()
    await ready(t)
    t.controller.send()
    expect(t.state().phase).toBe('starting')
    t.trips[0].resolve({ tripId: 't', started: true })
    await flush()
    expect(t.state().note).toBe(strings.startedTrip)
    expect(t.senders[0].job).toEqual({ frames: t.state().clip!.frames, fps: 10 })
    t.senders[0].emit({ type: 'progress', index: 0, sent: 1, skipped: 0 })
    expect(t.state().phase).toBe('sending')
    expect(t.preview.play).toHaveBeenCalledTimes(1)
    t.senders[0].emit({ type: 'progress', index: 122, sent: 123, skipped: 0 })
    expect(t.state().sentS).toBeCloseTo(12.3)
    t.senders[0].emit({ type: 'done', sent: 300, skipped: 0 })
    expect(t.state()).toMatchObject({ phase: 'ready', note: strings.sentSummary(300, 0) })
    expect(t.preview.pause).toHaveBeenCalled()
  })
  it('says when it sends into a trip that was already active', async () => {
    const t = setup()
    await sending(t, false)
    expect(t.state().note).toBe(strings.activeTrip)
  })
  it('ignores a second send while starting', async () => {
    const t = setup()
    await ready(t)
    t.controller.send()
    t.controller.send()
    expect(t.trips).toHaveLength(1)
    t.trips[0].resolve({ tripId: 't', started: true })
    await flush()
    expect(t.senders).toHaveLength(1)
  })
  it('shows a trip error and stays ready', async () => {
    const t = setup()
    await ready(t)
    t.controller.send()
    t.trips[0].reject(new Error(strings.errors.unreachable('http://localhost:8000')))
    await flush()
    expect(t.state()).toMatchObject({ phase: 'ready', error: strings.errors.unreachable('http://localhost:8000') })
    expect(t.senders).toHaveLength(0)
  })
  it('stop while starting never starts the sender', async () => {
    const t = setup()
    await ready(t)
    t.controller.send()
    t.controller.stop()
    expect(t.state().phase).toBe('ready')
    t.trips[0].resolve({ tripId: 't', started: true })
    await flush()
    expect(t.senders).toHaveLength(0)
    expect(t.state().phase).toBe('ready')
  })
  it('stop while sending stops the sender and keeps the last counts', async () => {
    const t = setup()
    await sending(t)
    t.senders[0].emit({ type: 'progress', index: 49, sent: 50, skipped: 0 })
    t.controller.stop()
    expect(t.senders[0].stop).toHaveBeenCalledTimes(1)
    expect(t.state()).toMatchObject({ phase: 'ready', note: strings.sentSummary(50, 0) })
    expect(t.preview.pause).toHaveBeenCalled()
    t.senders[0].emit({ type: 'done', sent: 300, skipped: 0 })
    expect(t.state().note).toBe(strings.sentSummary(50, 0))
  })
  it('a sender error ends the send with its message', async () => {
    const t = setup()
    await sending(t)
    t.senders[0].emit({ type: 'error', message: strings.errors.lost(12.3) })
    expect(t.state()).toMatchObject({ phase: 'ready', error: strings.errors.lost(12.3) })
    expect(t.preview.pause).toHaveBeenCalled()
  })
  it('choosing a file while sending stops the sender first', async () => {
    const t = setup()
    await sending(t)
    t.controller.chooseFile(file('b.mp4'))
    expect(t.senders[0].stop).toHaveBeenCalledTimes(1)
    t.senders[0].emit({ type: 'progress', index: 80, sent: 81, skipped: 0 })
    expect(t.state()).toMatchObject({ phase: 'preparing', clip: { name: 'b.mp4' } })
  })
  it('send() clears the last error and note', async () => {
    const t = setup()
    await sending(t)
    t.senders[0].emit({ type: 'error', message: 'x' })
    t.controller.send()
    expect(t.state()).toMatchObject({ phase: 'starting', error: null, note: null })
  })
  it('dispose() stops everything, frees the url and leaves the controller usable', async () => {
    const t = setup()
    await sending(t)
    t.controller.dispose()
    expect(t.senders[0].stop).toHaveBeenCalledTimes(1)
    expect(t.deps.objectUrl.revoke).toHaveBeenCalledWith('blob:1')
    expect(t.state().phase).toBe('empty')
    t.controller.chooseFile(file('c.mp4'))
    expect(t.state()).toMatchObject({ phase: 'preparing', clip: { name: 'c.mp4' } })
  })
})
```

- [ ] **Step 2: Run** `npm test -- controller`. Expected: FAIL (ne postoji `./controller`).
- [ ] **Step 3: Implementiraj `createController`.** Brojač pokušaja za izvlačenje i za slanje: svaki async nastavak i svaki događaj sendera prvo proveri da je njegov pokušaj još važeći, pa tek onda menja stanje. Stanje se menja samo zamenom objekta, posle čega se zovu slušaoci.
- [ ] **Step 4: Run** `npm test`. Expected: PASS (13 novih, ukupno 44).

---

### Task 6: Stranica u browseru, dokumentacija i e2e provera

**Files:**
- Modify: `src/lib/frames.ts` (dodaje `extractFrames`), `src/App.tsx`, `src/main.tsx`
- Create: `src/useVideoSim.ts`, `README.md`, `CLAUDE.md`
- Van app-a (privremeno, ne ide korisniku): `/home/claude/e2e/` (klipovi, lažni backend, Playwright skripta)

**Interfaces:**
- Consumes: sve iz Task 1–5.
- Produces: `extractFrames(file: File, onProgress: (done: number, total: number) => void, signal: AbortSignal): Promise<ExtractedClip>` u `frames.ts`; `useVideoSim(): { state: SimState; previewRef: RefObject<HTMLVideoElement | null>; chooseFile(file: File): void; send(): void; stop(): void }`.

- [ ] **Step 1: `extractFrames`.** Redom: `file.type` postoji i nije `video/*` → `notVideo`. `<video>` van DOM-a (`muted`, `playsInline`, `preload = 'auto'`, svoj object URL), čeka `loadeddata` (ne samo metadata, da frejm na 0 s već postoji); `error` → `cantDecode`. `duration` nije konačan → `currentTime = 1e101` i čekaj `durationchange` (WebM sa MediaRecorder-a). `durationError` → baci poruku. `videoWidth === 0` → `cantDecode`. Canvas veličine `fitSize(…, MAX_WIDTH)`. Za svako `t` iz `frameTimes(duration, FPS)`: ako je `signal.aborted` baci `signal.reason`; `seekTo(t)` (odmah ako je `|currentTime − t| < 1e-6` i `readyState ≥ HAVE_CURRENT_DATA`, inače postavi `currentTime` i čekaj `seeked`; 5 s bez odgovora → `cantDecode`); `drawImage`; `toBlob('image/jpeg', JPEG_QUALITY)`, veći od `MAX_FRAME_BYTES` → ponovo sa `FALLBACK_QUALITY`, i dalje veći → `frameTooBig`; `arrayBuffer()`; `onProgress(i + 1, total)`. U `finally` oslobodi URL i isprazni `<video>`.
- [ ] **Step 2: `useVideoSim`.** Kontroler se pravi jednom (`useState(() => createController(deps))`), stanje preko `useSyncExternalStore(subscribe, getState)`, `useEffect` cleanup zove `dispose`. Deps: `extract = extractFrames`, `ensureTrip = () => ensureTrip()`, `startSending = (job, onEvent) => startSending({ ...job, url: cameraSocketUrl() }, onEvent)`, `objectUrl = URL.createObjectURL/revokeObjectURL`, `preview` čita `previewRef.current` tek kad se pozove (`play`: `currentTime = 0`, `play().catch(() => {})`; `pause`), `fps = FPS`.
- [ ] **Step 3: `App.tsx` i `main.tsx`.** `<StrictMode>`. Stranica po specu (§ Stranica): naslov i podnaslov; `empty` = polje za prevlačenje i klik (skriven `<input type="file" accept="video/*">`, vrednost se briše posle izbora); u ostalim stanjima `<video ref={previewRef} src={clip.url} muted playsInline preload="auto">`, red `clipInfo`, traka pripreme (`preparing`), **Send** i **Choose another** (`ready`), `checkingTrip` i **Stop** (`starting`), traka `progress` i **Stop** (`sending`), pa red za `note` i red za `error` (`text-destructive`). Prevlačenje fajla radi na celoj stranici u svakom stanju. Samo tokeni iz `index.css`.
- [ ] **Step 4: `README.md` i `CLAUDE.md`** (engleski, kao ostali frontend app-ovi). README: šta je; pokretanje (`cp .env.example .env`, `npm install`, `npm run dev` → `http://localhost:5174`); pre testa ili demo-a (`python run.py`; model worker `python ..\model\worker.py` ili `--fake`; `SPEED_SCENARIO=cruise` u `backend/.env`; vožnju prvo pokreni sa telefona, inače sajt pokreće `video-sim` koja nije na nalogu; tab sme da bude u pozadini); kako radi (frejmovi unapred, worker, realno vreme, 10/s, JPEG 80 %, ≤ 1280 px, `WS /api/v1/camera/ws`, `POST /trips` samo kad vožnje nema); ograničenja (≤ 2 min; MP4 H.264 ili WebM; posle klipa telefon i dashboard ostaju na poslednjem stanju; ako telefon završi vožnju usred klipa, backend ostatak tiho odbacuje; ne puštaj istovremeno `tools/camera_stream.py`, frejmovi bi se mešali); testovi. CLAUDE.md: komande, mapa `src/`, pravila (tekst samo u `strings.ts`, backend se ne menja, realno vreme, zašto worker, testovi samo u Node-u) i zamke (seek na isto vreme, `Infinity` trajanje, `dispose` i StrictMode, Vite obrazac `new URL(…, import.meta.url)` za worker).
- [ ] **Step 5: Run** `npm test && npm run build && npm run lint`. Expected: 44 testa prolaze, build i lint bez grešaka.
- [ ] **Step 6: E2E pribor u `/home/claude/e2e/`.** Klipovi:
  `ffmpeg -y -f lavfi -i testsrc2=size=1920x1080:rate=30 -t 30 -c:v libx264 -pix_fmt yuv420p clip30.mp4`;
  `ffmpeg -y -f lavfi -i testsrc2=size=640x480:rate=30 -t 30 -c:v libvpx -b:v 1M -f webm -live 1 clip_live.webm` (`ffprobe` mora da pokaže `duration=N/A`);
  `ffmpeg -y -f lavfi -i testsrc2=size=320x240:rate=10 -t 150 -c:v libx264 -pix_fmt yuv420p clip150.mp4`; `notvideo.txt`;
  `broken.mp4` (`head -c 50000 /dev/urandom`).
  Lažni backend (Node + `ws`, `127.0.0.1:8000`): `GET /api/v1/coordinator/status`, `POST /api/v1/trips` (broji pozive), `WS /api/v1/camera/ws` (za svaku poruku: vreme dolaska, veličina, da li počinje sa `FF D8 FF`), plus `GET /__stats?from&to`, `POST /__reset?trip=none|active`, `POST /__drop` (zatvori sve camera socket-e), `POST /__down` / `__up` (status vraća grešku). Dev server: `VITE_API_URL=http://127.0.0.1:8000 npx vite --port 5174 --strictPort`.
- [ ] **Step 7: Run e2e** (Playwright, `/usr/bin/google-chrome-stable`, headless). Expected:
  - **S1** (nema vožnje, `clip30.mp4`): `300 frames · 30.0 s · 1280×720` → Send → `Started trip video-sim` → za ≤ 40 s `Sent 300 frames, 0 skipped`. Stats: 1 `POST /trips`, 300 frejmova, svih 300 JPEG, najveći < 2 000 000 B, od prvog do poslednjeg 29.4–30.4 s.
  - **S2** (vožnja postoji, dupli klik na Send): `Sending into the active trip`, 0 `POST /trips`; Stop posle ~3 s → `Sent N frames, 0 skipped` sa N = broj primljenih (25–35).
  - **S3** (`clip_live.webm`): red se poklapa sa `^(299|300) frames · (29.9|30.0) s · 640×480$`.
  - **S4** (slanje, pa glavna nit blokirana 3 s sa `page.evaluate`): u tom prozoru stiže ≥ 27 frejmova.
  - **S5** (`/__drop` usred slanja): za ≤ 2 s red počinje sa `Lost the connection to the backend after`, Send je aktivan, novi Send opet šalje frejmove.
  - **S6** (`clip150.mp4`): `The clip is longer than 2 minutes. Trim it first.` i vidi se polje za prevlačenje. **S7** (`notvideo.txt`): `That file is not a video.`; `broken.mp4` (`video/mp4`): `This browser can't decode the video. Export it as MP4 (H.264).`
  - **S8** (`/__down`, pa Send): `Backend not reachable at http://127.0.0.1:8000. Start it with python run.py.`
- [ ] **Step 8: Izgled.** Screenshot stanja ready i sending (iz S1), pregledaj ih: tokeni, raspored, čitljiv tekst, svetla i tamna tema (`colorScheme: 'dark'`).
- [ ] **Step 9: Kopiraj na laptop i proveri tamo.** `device_commit_files` za sve fajlove iz `frontend/video-sim/` osim `node_modules` i `dist` (sa `package-lock.json`). Na laptopu: `cd ~/mnt/frontend/video-sim && npm ci && npm test && npm run build && npm run lint`. Expected: sve prolazi.
