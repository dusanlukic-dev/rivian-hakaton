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
  ensureTrip(): Promise<{ tripId: string; started: boolean }>
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
  /** Only from `ready` */
  send(): void
  /** Only from `starting` or `sending` */
  stop(): void
  /** Stops everything and frees the URL, but stays usable: StrictMode runs effect cleanups once on mount in dev */
  dispose(): void
}

const INITIAL: SimState = { phase: 'empty', clip: null, prepared: null, sentS: 0, note: null, error: null }

const message = (error: unknown) => (error instanceof Error ? error.message : String(error))

/**
 * The page's flow: file → preparing → ready → starting → sending → ready. Every extraction and every send is a run
 * with its own number; a callback or sender event from an older run (a replaced file, a stopped send) is dropped.
 */
export function createController(deps: ControllerDeps): Controller {
  let state = INITIAL
  const listeners = new Set<() => void>()
  let extractRun = 0
  let abortExtract: AbortController | null = null
  let sendRun = 0
  let stopSender: (() => void) | null = null
  let lastCounts = { sent: 0, skipped: 0 }

  const set = (patch: Partial<SimState>) => {
    state = { ...state, ...patch }
    for (const listener of listeners) listener()
  }

  const cancelSend = () => {
    sendRun++
    stopSender?.()
    stopSender = null
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

  const send = () => {
    const clip = state.clip
    if (state.phase !== 'ready' || !clip) return
    cancelSend()
    const run = sendRun
    lastCounts = { sent: 0, skipped: 0 }
    set({ phase: 'starting', sentS: 0, note: null, error: null })

    deps
      .ensureTrip()
      .then(({ started }) => {
        if (run !== sendRun) return
        set({ note: started ? strings.startedTrip : strings.activeTrip })
        stopSender = deps.startSending({ frames: clip.frames, fps: deps.fps }, (event) => {
          if (run === sendRun) onSenderEvent(event)
        })
      })
      .catch((error: unknown) => {
        if (run !== sendRun) return
        set({ phase: 'ready', error: message(error) })
      })
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
    dispose,
  }
}
