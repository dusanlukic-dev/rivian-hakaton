import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { FPS } from '@/config'
import { cameraSocketUrl, ensureTrip } from '@/lib/backend'
import { createController } from '@/lib/controller'
import { extractFrames } from '@/lib/frames'
import { startSending } from '@/lib/sender'

/** The page's state and actions: the controller (lib/controller.ts) wired to the browser */
export function useVideoSim() {
  const previewRef = useRef<HTMLVideoElement | null>(null)
  const [controller] = useState(() =>
    createController({
      extract: extractFrames,
      ensureTrip: () => ensureTrip(),
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

  return { state, previewRef, chooseFile: controller.chooseFile, send: controller.send, stop: controller.stop }
}
