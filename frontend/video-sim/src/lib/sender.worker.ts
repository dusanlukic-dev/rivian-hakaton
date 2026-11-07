import { CONNECT_ATTEMPTS, CONNECT_RETRY_MS, MAX_BUFFERED_BYTES, PROGRESS_EVERY_MS } from '@/config'
import type { Clock } from './schedule'
import { runSender, type Connect, type SenderEvent, type WorkerRequest } from './senderCore'

// A dedicated worker: its timers and socket keep their pace when the page's tab is hidden and the main thread is
// throttled (e.g. on stage, with the dashboard in front)
const scope = self as unknown as {
  onmessage: ((event: MessageEvent<WorkerRequest>) => void) | null
  postMessage(event: SenderEvent): void
}

const clock: Clock = {
  now: () => performance.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
}

const connect: Connect = (url, handlers) => {
  const socket = new WebSocket(url)
  socket.binaryType = 'arraybuffer'
  socket.onopen = () => handlers.onOpen()
  socket.onclose = () => handlers.onClose()
  return {
    send: (data) => socket.send(data),
    bufferedAmount: () => socket.bufferedAmount,
    close: () => socket.close(),
  }
}

let stop: (() => void) | null = null

scope.onmessage = ({ data }) => {
  stop?.()
  stop = null
  if (data.type === 'start') {
    const { url, frames, fps } = data
    stop = runSender(
      { url, frames, fps },
      {
        connect,
        clock,
        maxBufferedBytes: MAX_BUFFERED_BYTES,
        progressEveryMs: PROGRESS_EVERY_MS,
        connectAttempts: CONNECT_ATTEMPTS,
        connectRetryMs: CONNECT_RETRY_MS,
      },
      (event) => scope.postMessage(event),
    )
  }
}
