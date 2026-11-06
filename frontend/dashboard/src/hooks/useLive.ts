import { useEffect, useRef, useState } from 'react'
import type { LiveMessage } from '@/api/types'
import { API_BASE_URL } from '@/utils/api/client'

/** `idle` = disabled · `connecting` = first attempt · `open` = live · `reconnecting` = dropped or failed, retrying */
export type LiveStatus = 'idle' | 'connecting' | 'open' | 'reconnecting'

export interface UseLiveOptions {
  /** Default `liveUrl()` */
  url?: string
  /** Every server message, parsed. Can be an inline function (read through a ref, never reconnects) */
  onMessage: (msg: LiveMessage) => void
  /** After every connect and reconnect. The server sends the current `state` right away if a trip is active */
  onOpen?: () => void
  /** false = no connection */
  enabled?: boolean
}

/**
 * The backend's live socket. Dev: same origin `/api/v1/ws`, which the Vite proxy forwards (ws: true) to VITE_API_URL.
 * Production build: VITE_API_URL's host directly.
 */
export function liveUrl(): string {
  const base = (API_BASE_URL || `${location.protocol}//${location.host}`).replace(/\/+$/, '')
  return `${base.replace(/^http/, 'ws')}/api/v1/ws`
}

/** Delay before reconnect attempt n: 1, 2, 4, 8 s, then every 10 s. Never gives up (docs/API.md §6) */
const backoff = (attempt: number) => Math.min(1000 * 2 ** attempt, 10_000)

/** Plain WebSocket to the backend (receive-only), with a never-give-up reconnect */
export function useLive({ url = liveUrl(), onMessage, onOpen, enabled = true }: UseLiveOptions) {
  // Keyed by url, so a status from a previous url never leaks into the new connection
  const [conn, setConn] = useState<{ url: string; status: LiveStatus }>({ url: '', status: 'connecting' })
  const handlers = useRef({ onMessage, onOpen })
  useEffect(() => {
    handlers.current = { onMessage, onOpen }
  })

  useEffect(() => {
    if (!enabled) return
    let ws: WebSocket | null = null
    let attempt = 0
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const open = () => {
      ws = new WebSocket(url)
      ws.onopen = () => {
        attempt = 0
        setConn({ url, status: 'open' })
        handlers.current.onOpen?.()
      }
      ws.onmessage = (event: MessageEvent<string>) => {
        let msg: LiveMessage
        try {
          msg = JSON.parse(event.data) as LiveMessage
        } catch {
          return
        }
        handlers.current.onMessage(msg)
      }
      // An error is always followed by close, so close alone drives the retries
      ws.onclose = () => {
        if (stopped) return
        setConn({ url, status: 'reconnecting' })
        timer = setTimeout(open, backoff(attempt++))
      }
    }

    // Deferred one tick, so StrictMode's throwaway first mount never opens a socket
    timer = setTimeout(open, 0)
    return () => {
      stopped = true
      clearTimeout(timer)
      ws?.close()
    }
  }, [url, enabled])

  const status: LiveStatus = !enabled ? 'idle' : conn.url === url ? conn.status : 'connecting'
  return { status }
}
