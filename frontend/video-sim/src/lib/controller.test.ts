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
