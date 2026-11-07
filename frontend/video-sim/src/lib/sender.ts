import { strings } from '@/strings'
import type { SendJob, SenderEvent, WorkerRequest } from './senderCore'

/**
 * Sends one clip from a fresh worker (sender.worker.ts). Events end with `done` or `error`, after which the worker
 * is gone. The returned function stops sending; nothing is reported after it.
 */
export function startSending(job: SendJob, onEvent: (event: SenderEvent) => void): () => void {
  const worker = new Worker(new URL('./sender.worker.ts', import.meta.url), { type: 'module' })
  let ended = false
  const end = () => {
    ended = true
    worker.terminate()
  }

  worker.onmessage = ({ data }: MessageEvent<SenderEvent>) => {
    if (ended) return
    if (data.type !== 'progress') end()
    onEvent(data)
  }
  worker.onerror = () => {
    if (ended) return
    end()
    onEvent({ type: 'error', message: strings.errors.senderCrashed })
  }

  worker.postMessage({ type: 'start', ...job } satisfies WorkerRequest)
  return () => {
    if (ended) return
    worker.postMessage({ type: 'stop' } satisfies WorkerRequest)
    end()
  }
}
