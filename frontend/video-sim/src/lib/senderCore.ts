import { strings } from '@/strings'
import { startSchedule, type Clock } from './schedule'

/** What the sender needs from a WebSocket: a real one in the worker, a fake in tests */
export interface Transport {
  send(data: ArrayBuffer): void
  /** Bytes queued but not sent yet */
  bufferedAmount(): number
  close(): void
}

export type Connect = (url: string, handlers: { onOpen(): void; onClose(): void }) => Transport

export interface SendJob {
  /** WS /api/v1/camera/ws of the backend */
  url: string
  /** One JPEG per binary message, frame i at i / fps seconds */
  frames: ArrayBuffer[]
  fps: number
}

/** Worker → page. `skipped` counts frames dropped for a late wake-up or a full socket buffer */
export type SenderEvent =
  | { type: 'progress'; index: number; sent: number; skipped: number }
  | { type: 'done'; sent: number; skipped: number }
  | { type: 'error'; message: string }

/** Page → worker */
export type WorkerRequest = ({ type: 'start' } & SendJob) | { type: 'stop' }

export interface SenderDeps {
  connect: Connect
  clock: Clock
  maxBufferedBytes: number
  progressEveryMs: number
  /** Tries in all for a socket that closes before it opens (the coordinator still counts the previous camera) */
  connectAttempts: number
  connectRetryMs: number
}

/**
 * Streams the frames over one socket in real time (startSchedule), like the camera does. After `done`, an `error`
 * or stop(), nothing more is reported and the socket is closed. Returns stop().
 */
export function runSender(job: SendJob, deps: SenderDeps, emit: (event: SenderEvent) => void): () => void {
  const { connect, clock, maxBufferedBytes, progressEveryMs, connectAttempts, connectRetryMs } = deps
  let opened = false
  let finished = false
  let attempts = 0
  let retry: unknown = null
  let stopSchedule: (() => void) | null = null
  let sent = 0
  let skipped = 0
  let lastIndex = -1
  let lastProgressAt = -Infinity

  const open = (): Transport => {
    attempts += 1
    const transport: Transport = connect(job.url, {
      onOpen() {
        if (finished) return
        opened = true
        stopSchedule = startSchedule({
          count: job.frames.length,
          fps: job.fps,
          clock,
          onFrame(index, skippedBefore) {
            skipped += skippedBefore
            if (transport.bufferedAmount() > maxBufferedBytes) {
              skipped += 1 // the backend is behind: drop this frame instead of queueing it
            } else {
              transport.send(job.frames[index])
              sent += 1
            }
            lastIndex = index
            const now = clock.now()
            if (now - lastProgressAt >= progressEveryMs) {
              lastProgressAt = now
              emit({ type: 'progress', index, sent, skipped })
            }
          },
          onDone() {
            finished = true
            emit({ type: 'done', sent, skipped })
            transport.close()
          },
        })
      },
      onClose() {
        if (finished) return
        if (!opened && attempts < connectAttempts) {
          retry = clock.setTimeout(() => {
            retry = null
            if (!finished) current = open()
          }, connectRetryMs)
          return
        }
        finished = true
        stopSchedule?.()
        emit({
          type: 'error',
          message: opened ? strings.errors.lost((lastIndex + 1) / job.fps) : strings.errors.cantConnect,
        })
      },
    })
    return transport
  }
  let current = open()

  return () => {
    if (finished) return
    finished = true
    if (retry !== null) clock.clearTimeout(retry)
    stopSchedule?.()
    current.close()
  }
}
