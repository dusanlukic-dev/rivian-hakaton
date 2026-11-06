import { useEffect, useRef, useState } from 'react'
import * as signalR from '@microsoft/signalr'

/** 'error' means the last attempt failed and another one is scheduled */
export type HubConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error'

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- matches HubConnection.on's own signature
type HubHandlers = Record<string, (...args: any[]) => void>

type UseSignalROptions = {
  /** Hub URL, e.g. `${API_BASE_URL}/hubs/queue` */
  url: string
  accessToken?: string | null
  /** Server → client events, e.g. `{ TicketCalled: (data) => ... }`. Safe to pass a new object every render. */
  handlers?: HubHandlers
  /**
   * Runs after every (re)connect. Join groups and refetch state here: groups are lost when the
   * connection drops, and anything the server sent while you were disconnected never arrives.
   */
  onConnected?: (connection: signalR.HubConnection) => Promise<void> | void
  enabled?: boolean
}

/** 0, 2, 5 s, then every 10 s forever. SignalR's own default gives up after 4 tries. */
const retryDelay = (attempt: number) => [0, 2_000, 5_000][attempt] ?? 10_000

export const useSignalR = ({
  url,
  accessToken,
  handlers = {},
  onConnected,
  enabled = true,
}: UseSignalROptions) => {
  const [state, setState] = useState<HubConnectionState>('disconnected')
  const [connection, setConnection] = useState<signalR.HubConnection | null>(null)

  // Latest callbacks without recreating the connection on every render
  const handlersRef = useRef(handlers)
  const onConnectedRef = useRef(onConnected)
  useEffect(() => {
    handlersRef.current = handlers
    onConnectedRef.current = onConnected
  })

  // Only reconnect when the set of event names changes, not the handler functions
  const eventNames = Object.keys(handlers).sort().join(',')

  useEffect(() => {
    if (!enabled) return

    let cancelled = false
    let startTimer: ReturnType<typeof setTimeout> | undefined
    // A torn-down connection can still resolve late (e.g. mid-onConnected) — it must not overwrite the new one's state
    const update = (next: HubConnectionState) => {
      if (!cancelled) setState(next)
    }

    const conn = new signalR.HubConnectionBuilder()
      .withUrl(url, {
        // Reaches negotiate (and long polling) only: browsers can't set headers on a WebSocket
        headers: { 'ngrok-skip-browser-warning': 'true' },
        ...(accessToken && { accessTokenFactory: () => accessToken }),
      })
      .withAutomaticReconnect({ nextRetryDelayInMilliseconds: ({ previousRetryCount }) => retryDelay(previousRetryCount) })
      .configureLogging(signalR.LogLevel.Warning)
      .build()

    for (const name of eventNames.split(',').filter(Boolean)) {
      conn.on(name, (...args) => handlersRef.current[name]?.(...args))
    }

    const runOnConnected = async () => {
      try {
        await onConnectedRef.current?.(conn)
      } catch (err) {
        // After teardown its invokes fail with "Invocation canceled", which is expected
        if (!cancelled) console.warn('[SignalR] onConnected failed:', err)
      }
    }

    conn.onreconnecting(() => update('reconnecting'))
    conn.onreconnected(async () => {
      await runOnConnected()
      update('connected')
    })
    // Only after stop() or a server-side close: the retry policy above never gives up
    conn.onclose(() => update('disconnected'))

    // withAutomaticReconnect only covers connections that were up, so retry a failed first start here
    const start = async (attempt: number) => {
      update('connecting')
      try {
        await conn.start()
      } catch (err) {
        if (cancelled) return
        const delay = retryDelay(attempt + 1)
        console.warn(`[SignalR] Connection failed, retrying in ${delay / 1000}s:`, err)
        update('error')
        startTimer = setTimeout(() => void start(attempt + 1), delay)
        return
      }
      if (cancelled) return
      await runOnConnected()
      if (cancelled) return
      setConnection(conn)
      setState('connected')
    }
    // Deferred so StrictMode's mount → unmount → mount never starts (and then aborts) a throwaway connection
    startTimer = setTimeout(() => void start(0), 0)

    return () => {
      cancelled = true
      clearTimeout(startTimer)
      setConnection(null)
      setState('disconnected')
      void conn.stop()
    }
  }, [url, accessToken, enabled, eventNames])

  return { connection, state }
}
