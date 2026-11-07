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
