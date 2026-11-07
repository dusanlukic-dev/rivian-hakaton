import type { Clock } from './schedule'

/**
 * What this page needs from the live socket (WS /api/v1/ws): when a trip starts and ends, and which trip has already
 * been scored (`ticked`: a `state` with a speed_source, which is null before the first tick, docs/API.md §4). A
 * ticked trip got frames from somewhere (this page before a reload, another camera), so its score no longer starts
 * at 100
 */
export type TripEvent =
  | { type: 'started'; tripId: string }
  | { type: 'ended'; tripId: string }
  | { type: 'ticked'; tripId: string }

/** A real WebSocket in the browser, a fake in tests */
export type OpenLive = (url: string, handlers: { onMessage(data: string): void; onClose(): void }) => { close(): void }

/**
 * One live message ({"type": LiveEvent, "data": ...}, docs/API.md) → a trip event, or null for everything else
 * (a state before the first tick, section, emergency, anything new)
 */
export function parseTripEvent(raw: string): TripEvent | null {
  try {
    const { type, data } = JSON.parse(raw) as { type?: unknown; data?: { trip_id?: unknown; speed_source?: unknown } }
    const tripId = data?.trip_id
    if (typeof tripId !== 'string') return null
    if (type === 'trip_started') return { type: 'started', tripId }
    if (type === 'trip_ended') return { type: 'ended', tripId }
    if (type === 'state' && data?.speed_source != null) return { type: 'ticked', tripId }
  } catch {
    // not JSON
  }
  return null
}

/**
 * Listens to the live socket and reports trip starts and ends; reconnects `retryMs` after the socket closes
 * (backend restart). The socket is event-driven, so it keeps working while the tab is hidden. Returns stop().
 */
export function watchTrips(
  deps: { url: string; open: OpenLive; clock: Pick<Clock, 'setTimeout' | 'clearTimeout'>; retryMs: number },
  onEvent: (event: TripEvent) => void,
): () => void {
  let stopped = false
  let retry: unknown = null
  let socket: { close(): void } | null = null

  const connect = () => {
    socket = deps.open(deps.url, {
      onMessage(data) {
        if (stopped) return
        const event = parseTripEvent(data)
        if (event) onEvent(event)
      },
      onClose() {
        if (stopped) return
        socket = null
        retry = deps.clock.setTimeout(() => {
          retry = null
          if (!stopped) connect()
        }, deps.retryMs)
      },
    })
  }
  connect()

  return () => {
    stopped = true
    if (retry !== null) deps.clock.clearTimeout(retry)
    socket?.close()
  }
}
