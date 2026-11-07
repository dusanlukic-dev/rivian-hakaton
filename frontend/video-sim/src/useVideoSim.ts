import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { FPS, LIVE_RETRY_MS } from '@/config'
import { cameraSocketUrl, getActiveTrip, liveSocketUrl, startTrip } from '@/lib/backend'
import { createController } from '@/lib/controller'
import { extractFrames } from '@/lib/frames'
import { startSending } from '@/lib/sender'
import { watchTrips, type OpenLive } from '@/lib/tripEvents'

const openLive: OpenLive = (url, handlers) => {
  const socket = new WebSocket(url)
  socket.onmessage = ({ data }) => {
    if (typeof data === 'string') handlers.onMessage(data)
  }
  socket.onclose = () => handlers.onClose()
  return { close: () => socket.close() }
}

const timers = {
  setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms),
  clearTimeout: (handle: unknown) => clearTimeout(handle as ReturnType<typeof setTimeout>),
}

/** The page's state and actions: the controller (lib/controller.ts) wired to the browser */
export function useVideoSim() {
  const previewRef = useRef<HTMLVideoElement | null>(null)
  const [controller] = useState(() =>
    createController({
      extract: extractFrames,
      getActiveTrip,
      startTrip: async () => (await startTrip()).trip_id,
      startSending: (job, onEvent) => startSending({ ...job, url: cameraSocketUrl() }, onEvent),
      objectUrl: { create: (file) => URL.createObjectURL(file), revoke: (url) => URL.revokeObjectURL(url) },
      // Read only when the controller calls it, never during render
      preview: () => {
        const video = previewRef.current
        if (!video) return null
        return {
          play: () => {
            video.currentTime = 0
            video.play().catch(() => undefined) // a muted preview may still be refused; sending doesn't depend on it
          },
          pause: () => video.pause(),
        }
      },
      fps: FPS,
    }),
  )
  const state = useSyncExternalStore(controller.subscribe, controller.getState)
  useEffect(() => () => controller.dispose(), [controller])
  // Trip starts and ends from the coordinator: a trip the phone starts gets the loaded clip from the start
  useEffect(
    () =>
      watchTrips({ url: liveSocketUrl(), open: openLive, clock: timers, retryMs: LIVE_RETRY_MS }, (event) => {
        if (event.type === 'started') controller.tripStarted(event.tripId)
        else if (event.type === 'ended') controller.tripEnded(event.tripId)
        else controller.tripTicked(event.tripId)
      }),
    [controller],
  )

  return { state, previewRef, chooseFile: controller.chooseFile, send: controller.send, stop: controller.stop }
}
