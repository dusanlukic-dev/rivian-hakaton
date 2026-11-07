import { describe, expect, it } from 'vitest'
import { FakeClock } from '@/test/fakeClock'
import { parseTripEvent, watchTrips, type OpenLive, type TripEvent } from './tripEvents'

const live = (type: string, data: unknown) => JSON.stringify({ type, data })

describe('parseTripEvent', () => {
  it('reads trip_started and trip_ended', () => {
    expect(parseTripEvent(live('trip_started', { trip_id: 'a', score: 100 }))).toEqual({ type: 'started', tripId: 'a' })
    expect(parseTripEvent(live('trip_ended', { trip_id: 'a', average_score: 80 }))).toEqual({ type: 'ended', tripId: 'a' })
  })
  it('reads a state after the first tick as ticked', () => {
    expect(parseTripEvent(live('state', { trip_id: 'a', speed_source: 'mock' }))).toEqual({ type: 'ticked', tripId: 'a' })
  })
  it('ignores a state before the first tick, section, emergency, unknown events and junk', () => {
    expect(parseTripEvent(live('state', { trip_id: 'a', status: 'active', speed_source: null }))).toBeNull()
    expect(parseTripEvent(live('section', { trip_id: 'a' }))).toBeNull()
    expect(parseTripEvent(live('emergency', { trip_id: 'a' }))).toBeNull()
    expect(parseTripEvent(live('trip_started', {}))).toBeNull()
    expect(parseTripEvent('not json')).toBeNull()
  })
})

class FakeLive {
  urls: string[] = []
  closed = 0
  handlers: { onMessage(data: string): void; onClose(): void } | null = null
  open: OpenLive = (url, handlers) => {
    this.urls.push(url)
    this.handlers = handlers
    return { close: () => void (this.closed += 1) }
  }
}

function setup() {
  const clock = new FakeClock()
  const socket = new FakeLive()
  const events: TripEvent[] = []
  const stop = watchTrips({ url: 'ws://car/api/v1/ws', open: socket.open, clock, retryMs: 2000 }, (e) => void events.push(e))
  return { clock, socket, events, stop }
}

describe('watchTrips', () => {
  it('reports trip starts and ends from the live socket', () => {
    const { socket, events } = setup()
    expect(socket.urls).toEqual(['ws://car/api/v1/ws'])
    socket.handlers!.onMessage(live('state', { trip_id: 'a', status: 'active' }))
    socket.handlers!.onMessage(live('trip_ended', { trip_id: 'a' }))
    socket.handlers!.onMessage(live('trip_started', { trip_id: 'b' }))
    expect(events).toEqual([
      { type: 'ended', tripId: 'a' },
      { type: 'started', tripId: 'b' },
    ])
  })
  it('reconnects after the socket closes', () => {
    const { clock, socket } = setup()
    socket.handlers!.onClose()
    clock.advance(1999)
    expect(socket.urls).toHaveLength(1)
    clock.advance(1)
    expect(socket.urls).toHaveLength(2)
  })
  it('stop() closes the socket, cancels a pending reconnect and reports nothing more', () => {
    const { clock, socket, events, stop } = setup()
    const handlers = socket.handlers!
    handlers.onClose()
    stop()
    clock.advance(5000)
    expect(socket.urls).toHaveLength(1)
    handlers.onMessage(live('trip_started', { trip_id: 'b' }))
    expect(events).toEqual([])
  })
})
