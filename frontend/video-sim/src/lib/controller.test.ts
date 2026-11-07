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

function setup() {
  const extractions: { onProgress: (d: number, t: number) => void; signal: AbortSignal; result: ReturnType<typeof deferred<ExtractedClip>> }[] = []
  const actives: ReturnType<typeof deferred<string | null>>[] = []
  const starts: ReturnType<typeof deferred<string>>[] = []
  const senders: { job: { frames: ArrayBuffer[]; fps: number }; emit: (e: SenderEvent) => void; stop: ReturnType<typeof vi.fn> }[] = []
  const preview = { play: vi.fn(), pause: vi.fn() }
  let urls = 0
  const deps: ControllerDeps = {
    extract: (_f, onProgress, signal) => {
      const result = deferred<ExtractedClip>()
      extractions.push({ onProgress, signal, result })
      return result.promise
    },
    getActiveTrip: () => {
      const d = deferred<string | null>()
      actives.push(d)
      return d.promise
    },
    startTrip: () => {
      const d = deferred<string>()
      starts.push(d)
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
  return { controller, deps, extractions, actives, starts, senders, preview, state: () => controller.getState() }
}
type T = ReturnType<typeof setup>
async function ready(t: T, name = 'clip.mp4') {
  t.controller.chooseFile(file(name))
  t.extractions.at(-1)!.result.resolve(clip())
  await flush()
}
/** Send with `active` as the trip in progress; a POST /trips it makes gets `newTrip` */
async function send(t: T, active: string | null, newTrip = 'n1') {
  const starts = t.starts.length
  t.controller.send()
  t.actives.at(-1)!.resolve(active)
  await flush()
  if (t.starts.length > starts) {
    t.starts.at(-1)!.resolve(newTrip)
    await flush()
  }
}
async function sending(t: T, active: string | null = null) {
  await ready(t)
  await send(t, active)
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
  it('sends: no trip in progress, so it starts one, follows progress and ends ready', async () => {
    const t = setup()
    await ready(t)
    t.controller.send()
    expect(t.state().phase).toBe('starting')
    t.actives[0].resolve(null)
    await flush()
    expect(t.starts).toHaveLength(1)
    t.starts[0].resolve('n1')
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
  it('sends into the trip in progress while it has had no clip', async () => {
    const t = setup()
    await sending(t, 'p1')
    expect(t.starts).toHaveLength(0)
    expect(t.state().note).toBe(strings.activeTrip)
  })
  it('never sends a second clip into the same trip: Send then starts a new trip', async () => {
    const t = setup()
    await sending(t, 'p1')
    t.senders[0].emit({ type: 'done', sent: 300, skipped: 0 })
    await send(t, 'p1', 'n2')
    expect(t.starts).toHaveLength(1)
    expect(t.state().note).toBe(strings.startedTrip)
    expect(t.senders).toHaveLength(2)
    t.senders[1].emit({ type: 'done', sent: 300, skipped: 0 })
    await send(t, 'n2', 'n3') // its own new trip is used as well
    expect(t.starts).toHaveLength(2)
  })
  it('a trip that was already scored (another camera, a reload) is not used: Send starts a new trip', async () => {
    const t = setup()
    await ready(t)
    t.controller.tripTicked('p1')
    await send(t, 'p1', 'n1')
    expect(t.starts).toHaveLength(1)
    expect(t.state().note).toBe(strings.startedTrip)
  })
  it('a trip started by the phone gets the loaded clip from the start', async () => {
    const t = setup()
    await ready(t)
    t.controller.tripStarted('p2')
    expect(t.senders).toHaveLength(1)
    expect(t.state()).toMatchObject({ phase: 'starting', note: strings.phoneTrip, sentS: 0 })
    t.senders[0].emit({ type: 'progress', index: 0, sent: 1, skipped: 0 })
    expect(t.preview.play).toHaveBeenCalledTimes(1)
  })
  it('a new phone trip mid-clip restarts the clip in the new trip', async () => {
    const t = setup()
    await sending(t, 'p1')
    t.senders[0].emit({ type: 'progress', index: 99, sent: 100, skipped: 0 })
    t.controller.tripEnded('p1') // the coordinator ends the old trip first
    t.controller.tripStarted('p2')
    expect(t.senders[0].stop).toHaveBeenCalledTimes(1)
    expect(t.senders).toHaveLength(2)
    expect(t.state()).toMatchObject({ phase: 'starting', note: strings.phoneTrip, sentS: 0 })
    t.senders[0].emit({ type: 'progress', index: 120, sent: 121, skipped: 0 })
    expect(t.state().phase).toBe('starting') // the old sender's events are dropped
    t.senders[1].emit({ type: 'progress', index: 0, sent: 1, skipped: 0 })
    expect(t.state()).toMatchObject({ phase: 'sending', sentS: 0.1 })
  })
  it('a phone trip mid-clip without a trip_ended first still switches', async () => {
    const t = setup()
    await sending(t, 'p1')
    t.controller.tripStarted('p2')
    expect(t.senders[0].stop).toHaveBeenCalledTimes(1)
    expect(t.senders).toHaveLength(2)
  })
  it('ignores trip_started of its own new trip, of used trips and without a ready clip', async () => {
    const t = setup()
    t.controller.tripStarted('x0') // no clip
    t.controller.chooseFile(file())
    t.controller.tripStarted('x1') // still preparing
    t.extractions[0].result.resolve(clip())
    await flush()
    expect(t.senders).toHaveLength(0)

    t.controller.send()
    t.actives[0].resolve(null)
    await flush()
    t.controller.tripStarted('n1') // arrives before the POST /trips response
    t.starts[0].resolve('n1')
    await flush()
    t.controller.tripStarted('n1') // or after it
    expect(t.senders).toHaveLength(1)
  })
  it('Stop during its own POST /trips: the new trip does not start the clip by itself', async () => {
    const t = setup()
    await ready(t)
    t.controller.send()
    t.actives[0].resolve(null)
    await flush()
    t.controller.stop()
    t.starts[0].resolve('n1')
    await flush()
    t.controller.tripStarted('n1')
    expect(t.senders).toHaveLength(0)
    expect(t.state().phase).toBe('ready')
  })
  it('trip_ended of the trip it sends into stops sending; other trips are ignored', async () => {
    const t = setup()
    await sending(t, 'p1')
    t.controller.tripEnded('other')
    expect(t.state().phase).toBe('sending')
    t.controller.tripEnded('p1')
    expect(t.senders[0].stop).toHaveBeenCalledTimes(1)
    expect(t.state()).toMatchObject({ phase: 'ready', note: strings.tripEnded })
    expect(t.preview.pause).toHaveBeenCalled()
  })
  it('trip_ended after the clip is done changes nothing', async () => {
    const t = setup()
    await sending(t, 'p1')
    t.senders[0].emit({ type: 'done', sent: 300, skipped: 0 })
    t.controller.tripEnded('p1')
    expect(t.state()).toMatchObject({ phase: 'ready', note: strings.sentSummary(300, 0) })
  })
  it('ignores a second send while starting', async () => {
    const t = setup()
    await ready(t)
    t.controller.send()
    t.controller.send()
    expect(t.actives).toHaveLength(1)
    t.actives[0].resolve('p1')
    await flush()
    expect(t.senders).toHaveLength(1)
  })
  it('shows a trip error and stays ready', async () => {
    const t = setup()
    await ready(t)
    t.controller.send()
    t.actives[0].reject(new Error(strings.errors.unreachable('http://localhost:8000')))
    await flush()
    expect(t.state()).toMatchObject({ phase: 'ready', error: strings.errors.unreachable('http://localhost:8000') })
    expect(t.senders).toHaveLength(0)
  })
  it('shows a failed POST /trips and stays ready', async () => {
    const t = setup()
    await ready(t)
    t.controller.send()
    t.actives[0].resolve(null)
    await flush()
    t.starts[0].reject(new Error(strings.errors.tripFailed('HTTP 500')))
    await flush()
    expect(t.state()).toMatchObject({ phase: 'ready', error: strings.errors.tripFailed('HTTP 500') })
  })
  it('stop while starting never starts the sender', async () => {
    const t = setup()
    await ready(t)
    t.controller.send()
    t.controller.stop()
    expect(t.state().phase).toBe('ready')
    t.actives[0].resolve('p1')
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
