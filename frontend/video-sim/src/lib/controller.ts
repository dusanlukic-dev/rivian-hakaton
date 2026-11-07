import { strings } from '@/strings'
import type { ExtractedClip } from './frames'
import type { SendJob, SenderEvent } from './senderCore'

export type Phase = 'empty' | 'preparing' | 'ready' | 'starting' | 'sending'

export interface Clip {
  name: string
  /** Object URL of the file, for the preview */
  url: string
  /** Empty until the clip is ready */
  frames: ArrayBuffer[]
  durationS: number
  width: number
  height: number
}

export interface SimState {
  phase: Phase
  /** Set from `preparing` on */
  clip: Clip | null
  prepared: { done: number; total: number } | null
  /** Seconds of the clip sent so far: (index + 1) / fps of the latest progress */
  sentS: number
  note: string | null
  error: string | null
}

export interface ControllerDeps {
  extract(file: File, onProgress: (done: number, total: number) => void, signal: AbortSignal): Promise<ExtractedClip>
  /** The trip the coordinator runs now, or null */
  getActiveTrip(): Promise<string | null>
  /** Starts a new trip (the coordinator ends the one in progress) and returns its id */
  startTrip(): Promise<string>
  startSending(job: Omit<SendJob, 'url'>, onEvent: (event: SenderEvent) => void): () => void
  objectUrl: { create(file: File): string; revoke(url: string): void }
  /** The preview <video>, once it is on the page */
  preview(): { play(): void; pause(): void } | null
  fps: number
}

export interface Controller {
  /** The same object until something changes (useSyncExternalStore) */
  getState(): SimState
  subscribe(listener: () => void): () => void
  chooseFile(file: File): void
  /** Only from `ready`. Into the trip in progress if it hasn't had a clip yet, otherwise into a new trip */
  send(): void
  /** Only from `starting` or `sending` */
  stop(): void
  /** WS trip_started: a trip someone else started (the phone) gets the loaded clip from the start */
  tripStarted(tripId: string): void
  /** WS trip_ended: sending into that trip stops */
  tripEnded(tripId: string): void
  /** WS state after the first tick: the trip already had frames, so Send won't use it */
  tripTicked(tripId: string): void
  /** Stops everything and frees the URL, but stays usable: StrictMode runs effect cleanups once on mount in dev */
  dispose(): void
}

const INITIAL: SimState = { phase: 'empty', clip: null, prepared: null, sentS: 0, note: null, error: null }

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

/**
 * The page's flow: file → preparing → ready → starting → sending → ready. Every extraction and every send is a run
 * with its own number; a callback or sender event from an older run (a replaced file, a stopped send) is dropped.
 *
 * One clip = one trip: a trip that already got a clip from this page never gets another one, because the score has to
 * start at 100 with every clip (the coordinator starts every trip fresh: score, risk engine, model). So Send starts a
 * new trip unless the trip in progress is still unused, and a trip the phone starts gets the loaded clip at once.
 */
export function createController(deps: ControllerDeps): Controller {
  let state = INITIAL
  const listeners = new Set<() => void>()
  let extractRun = 0
  let abortExtract: AbortController | null = null
  let sendRun = 0
  let stopSender: (() => void) | null = null
  let lastCounts = { sent: 0, skipped: 0 }
  /** Trips that already got a clip from this page, or were scored before (tripTicked) */
  const usedTrips = new Set<string>()
  /** The trip the running send goes into */
  let sendingTrip: string | null = null
  /** POST /trips calls of this page in flight: their trip_started arrives before the response, and isn't the phone's */
  let ownStarts = 0

  const set = (patch: Partial<SimState>) => {
    state = { ...state, ...patch }
    for (const listener of listeners) listener()
  }

  const cancelSend = () => {
    sendRun++
    stopSender?.()
    stopSender = null
    sendingTrip = null
  }

  const cancelExtract = () => {
    extractRun++
    abortExtract?.abort()
    abortExtract = null
  }

  const dropClip = () => {
    if (state.clip) deps.objectUrl.revoke(state.clip.url)
  }

  /** The sender ended by itself (done or error): its events after this one are dropped */
  const finishSend = (patch: Partial<SimState>) => {
    sendRun++
    stopSender = null
    sendingTrip = null
    deps.preview()?.pause()
    set({ phase: 'ready', ...patch })
  }

  const onSenderEvent = (event: SenderEvent) => {
    switch (event.type) {
      case 'progress':
        lastCounts = { sent: event.sent, skipped: event.skipped }
        if (state.phase === 'starting') deps.preview()?.play() // the first frame is out: the preview starts with it
        set({ phase: 'sending', sentS: (event.index + 1) / deps.fps })
        break
      case 'done':
        finishSend({ note: strings.sentSummary(event.sent, event.skipped) })
        break
      case 'error':
        finishSend({ error: event.message })
        break
    }
  }

  const chooseFile = (file: File) => {
    if (state.phase === 'starting' || state.phase === 'sending') {
      cancelSend()
      deps.preview()?.pause()
    }
    cancelExtract()
    dropClip()
    const run = extractRun
    const abort = new AbortController()
    abortExtract = abort
    const url = deps.objectUrl.create(file)
    set({ ...INITIAL, phase: 'preparing', clip: { name: file.name, url, frames: [], durationS: 0, width: 0, height: 0 } })

    deps
      .extract(file, (done, total) => run === extractRun && set({ prepared: { done, total } }), abort.signal)
      .then((extracted) => {
        if (run !== extractRun || !state.clip) return
        abortExtract = null
        set({ phase: 'ready', prepared: null, clip: { ...state.clip, ...extracted } })
      })
      .catch((error: unknown) => {
        if (run !== extractRun) return
        abortExtract = null
        deps.objectUrl.revoke(url)
        set({ ...INITIAL, error: message(error) })
      })
  }

  /** Streams the clip from its first frame into `tripId`, which counts as used from now on */
  const beginSend = (clip: Clip, tripId: string, note: string) => {
    const run = sendRun
    usedTrips.add(tripId)
    sendingTrip = tripId
    lastCounts = { sent: 0, skipped: 0 }
    set({ phase: 'starting', sentS: 0, note, error: null })
    stopSender = deps.startSending({ frames: clip.frames, fps: deps.fps }, (event) => {
      if (run === sendRun) onSenderEvent(event)
    })
  }

  /** The unused trip in progress, or a new one */
  const pickTrip = async (run: number): Promise<{ tripId: string; note: string } | null> => {
    const active = await deps.getActiveTrip()
    if (run !== sendRun) return null
    if (active && !usedTrips.has(active)) return { tripId: active, note: strings.activeTrip }
    ownStarts++
    try {
      const tripId = await deps.startTrip()
      usedTrips.add(tripId) // even if Stop came meanwhile: its trip_started must not start the clip by itself
      return run === sendRun ? { tripId, note: strings.startedTrip } : null
    } finally {
      ownStarts--
    }
  }

  const send = () => {
    const clip = state.clip
    if (state.phase !== 'ready' || !clip) return
    cancelSend()
    const run = sendRun
    set({ phase: 'starting', sentS: 0, note: null, error: null })

    pickTrip(run)
      .then((picked) => {
        if (picked && run === sendRun) beginSend(clip, picked.tripId, picked.note)
      })
      .catch((error: unknown) => {
        if (run !== sendRun) return
        set({ phase: 'ready', error: message(error) })
      })
  }

  const tripStarted = (tripId: string) => {
    const clip = state.clip
    if (!clip || ownStarts > 0 || usedTrips.has(tripId)) return
    if (state.phase !== 'ready' && state.phase !== 'starting' && state.phase !== 'sending') return
    cancelSend() // a clip still running belongs to the previous trip: the new one gets it from the start
    deps.preview()?.pause()
    beginSend(clip, tripId, strings.phoneTrip)
  }

  const tripEnded = (tripId: string) => {
    if (sendingTrip !== tripId) return
    cancelSend()
    deps.preview()?.pause()
    set({ phase: 'ready', note: strings.tripEnded })
  }

  const stop = () => {
    if (state.phase !== 'starting' && state.phase !== 'sending') return
    const wasSending = state.phase === 'sending'
    cancelSend()
    deps.preview()?.pause()
    set({ phase: 'ready', note: wasSending ? strings.sentSummary(lastCounts.sent, lastCounts.skipped) : null })
  }

  const dispose = () => {
    cancelSend()
    cancelExtract()
    deps.preview()?.pause()
    dropClip()
    set(INITIAL)
  }

  return {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
    chooseFile,
    send,
    stop,
    tripStarted,
    tripEnded,
    tripTicked: (tripId) => void usedTrips.add(tripId),
    dispose,
  }
}
