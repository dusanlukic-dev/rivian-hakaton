import { wsUrl } from './address';
import type { LiveMessage } from './types';

export type LiveStatus = 'connecting' | 'open' | 'closed';

export interface LiveHandlers {
  onMessage(message: LiveMessage): void;
  onStatus(status: LiveStatus): void;
}

export interface LiveConnection {
  stop(): void;
  /** Reconnect right away if the socket is down (e.g. app came back to the foreground). */
  kick(): void;
}

/**
 * Keeps a WebSocket to the car computer open forever (docs/API.md §6): reconnects with
 * backoff 0.5 → 1 → 2 → 4 → 5 s. The server pushes the current `state` right after (re)connecting.
 */
export function connectLive(address: string, handlers: LiveHandlers): LiveConnection {
  let ws: WebSocket | null = null;
  let attempt = 0;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const open = () => {
    clearTimeout(timer);
    if (stopped) return;
    handlers.onStatus('connecting');
    const socket = new WebSocket(wsUrl(address));
    ws = socket;
    socket.onopen = () => {
      attempt = 0;
      handlers.onStatus('open');
    };
    socket.onmessage = (event) => {
      let message: LiveMessage;
      try {
        message = JSON.parse(String(event.data)) as LiveMessage;
      } catch {
        return; // ignore anything that isn't JSON
      }
      handlers.onMessage(message);
    };
    socket.onclose = () => {
      if (stopped || ws !== socket) return;
      ws = null;
      handlers.onStatus('closed');
      timer = setTimeout(open, Math.min(500 * 2 ** attempt++, 5000));
    };
  };

  open();

  return {
    stop() {
      stopped = true;
      clearTimeout(timer);
      const socket = ws;
      ws = null;
      socket?.close();
    },
    kick() {
      if (stopped || (ws && ws.readyState !== WebSocket.CLOSED)) return;
      attempt = 0;
      open();
    },
  };
}
