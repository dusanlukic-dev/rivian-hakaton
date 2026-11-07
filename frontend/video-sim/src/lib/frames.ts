import { FALLBACK_QUALITY, FPS, JPEG_QUALITY, MAX_DURATION_S, MAX_FRAME_BYTES, MAX_WIDTH } from '@/config'
import { strings } from '@/strings'

/** Longest wait for one media event (loading, a seek) before the file counts as undecodable */
const MEDIA_TIMEOUT_MS = 5000

/** A clip turned into camera frames, ready to send */
export interface ExtractedClip {
  /** One JPEG per frame, frame i belongs at i / FPS seconds */
  frames: ArrayBuffer[]
  durationS: number
  width: number
  height: number
}

/** Video times of the frames to send: floor(duration × fps) of them (at least one), 1 / fps apart */
export function frameTimes(durationS: number, fps: number): number[] {
  // The epsilon absorbs durations like 29.9999999 that mean 30 s
  const count = Math.max(1, Math.floor(durationS * fps + 1e-6))
  return Array.from({ length: count }, (_, i) => i / fps)
}

/** Scales down to maxWidth keeping the aspect ratio. Never scales up */
export function fitSize(width: number, height: number, maxWidth: number): { width: number; height: number } {
  if (width <= maxWidth) return { width, height }
  return { width: maxWidth, height: Math.round((height * maxWidth) / width) }
}

/** The message for a clip this site can't send, null when the duration is fine */
export function durationError(durationS: number): string | null {
  if (!Number.isFinite(durationS) || durationS <= 0) return strings.errors.cantDecode
  if (durationS > MAX_DURATION_S) return strings.errors.tooLong
  return null
}

/** Resolves on `event`; an `error` event or no event within the timeout means the browser can't decode the file */
function waitFor(video: HTMLVideoElement, event: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const finish = (ok: boolean) => {
      clearTimeout(timer)
      video.removeEventListener(event, onEvent)
      video.removeEventListener('error', onError)
      if (ok) resolve()
      else reject(new Error(strings.errors.cantDecode))
    }
    const onEvent = () => finish(true)
    const onError = () => finish(false)
    const timer = setTimeout(() => finish(false), MEDIA_TIMEOUT_MS)
    video.addEventListener(event, onEvent)
    video.addEventListener('error', onError)
  })
}

/** Setting currentTime to the time it already shows may never fire `seeked`, so that case returns at once */
async function seekTo(video: HTMLVideoElement, t: number): Promise<void> {
  if (Math.abs(video.currentTime - t) < 1e-6 && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) return
  const seeked = waitFor(video, 'seeked')
  video.currentTime = t
  await seeked
}

/** The canvas is copied when toBlob is called, so the next frame may be drawn before this encode finishes */
function encodeJpeg(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error(strings.errors.cantDecode))), 'image/jpeg', quality),
  )
}

/** JPEG of the canvas as it is now; a frame over MAX_FRAME_BYTES is re-encoded from its own JPEG */
async function encodeFrame(canvas: HTMLCanvasElement): Promise<ArrayBuffer> {
  const jpeg = await encodeJpeg(canvas, JPEG_QUALITY)
  if (jpeg.size <= MAX_FRAME_BYTES) return jpeg.arrayBuffer()
  // The canvas already shows a later frame by now, so this one is shrunk from the JPEG itself
  const bitmap = await createImageBitmap(jpeg)
  const again = document.createElement('canvas')
  again.width = bitmap.width
  again.height = bitmap.height
  again.getContext('2d')?.drawImage(bitmap, 0, 0)
  bitmap.close()
  const smaller = await encodeJpeg(again, FALLBACK_QUALITY)
  if (smaller.size > MAX_FRAME_BYTES) throw new Error(strings.errors.frameTooBig)
  return smaller.arrayBuffer()
}

/**
 * Playback speed while preparing. At 4× a 60 Hz screen presents about every other frame of a 30 fps clip (gaps up to
 * ~130 ms), so a target can get a frame a little late or, now and then, the same frame as its neighbour. Only when
 * presented frames are more than SKIP_TOLERANCE targets apart does the speed halve (down to 1×).
 */
const CAPTURE_RATE = 4
const SKIP_TOLERANCE = 2.5

/**
 * Plays the clip and calls take(i) for every target time, with the frame on screen: the first presented frame at or
 * after times[i] (requestVideoFrameCallback). Playing decodes every frame once; seeking per frame would decode from
 * the previous keyframe each time, which takes minutes for clips with sparse keyframes.
 */
function captureFrames(video: HTMLVideoElement, times: number[], take: (index: number) => void, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const interval = 1 / FPS
    let next = 0
    let last = video.currentTime
    let handle = 0
    const takeUpTo = (mediaTime: number) => {
      while (next < times.length && times[next] <= mediaTime + 1e-3) take(next++)
    }
    const finish = (error?: unknown) => {
      video.cancelVideoFrameCallback(handle)
      video.removeEventListener('ended', onEnded)
      video.removeEventListener('error', onError)
      signal.removeEventListener('abort', onAbort)
      video.pause()
      if (error === undefined) resolve()
      else reject(error)
    }
    const onFrame = (_now: number, frame: VideoFrameCallbackMetadata) => {
      if (frame.mediaTime - last > SKIP_TOLERANCE * interval && video.playbackRate > 1) {
        video.playbackRate = Math.max(1, video.playbackRate / 2) // whole targets are being skipped: slow down
      }
      last = frame.mediaTime
      takeUpTo(frame.mediaTime)
      if (next >= times.length) finish()
      else handle = video.requestVideoFrameCallback(onFrame)
    }
    // The last frame stays on screen after the end: it covers whatever targets are left
    const onEnded = () => {
      takeUpTo(Infinity)
      finish()
    }
    const onError = () => finish(new Error(strings.errors.cantDecode))
    const onAbort = () => finish(signal.reason)

    takeUpTo(video.currentTime) // the frame at 0 s is on screen already
    if (next >= times.length) return finish()
    video.addEventListener('ended', onEnded)
    video.addEventListener('error', onError)
    signal.addEventListener('abort', onAbort)
    handle = video.requestVideoFrameCallback(onFrame)
    video.playbackRate = CAPTURE_RATE
    video.play().catch(() => finish(new Error(strings.errors.cantDecode)))
  })
}

/**
 * Decodes the clip in the browser and turns it into camera frames: one JPEG per frameTimes() moment, at most MAX_WIDTH
 * wide. Runs right after the file is chosen, while the tab is visible, so sending never waits on decoding.
 * Throws an Error whose message is the user-facing text, or `signal.reason` once aborted.
 */
export async function extractFrames(
  file: File,
  onProgress: (done: number, total: number) => void,
  signal: AbortSignal,
): Promise<ExtractedClip> {
  if (file.type && !file.type.startsWith('video/')) throw new Error(strings.errors.notVideo)
  const src = URL.createObjectURL(file)
  const video = document.createElement('video')
  video.muted = true
  video.playsInline = true
  video.preload = 'auto'
  // On the page (tiny, nearly transparent): requestVideoFrameCallback only runs for frames the browser presents
  Object.assign(video.style, {
    position: 'fixed',
    right: '0',
    bottom: '0',
    width: '2px',
    height: '2px',
    opacity: '0.01',
    pointerEvents: 'none',
  })
  document.body.append(video)
  try {
    // loadeddata, not just metadata: the frame at 0 s must exist before the first draw
    const loaded = waitFor(video, 'loadeddata')
    video.src = src
    await loaded
    if (!Number.isFinite(video.duration)) {
      // WebM from MediaRecorder carries no duration; seeking far makes the browser scan the file and find it
      const found = waitFor(video, 'durationchange')
      video.currentTime = 1e101
      await found
      await seekTo(video, 0)
    }
    const problem = durationError(video.duration)
    if (problem) throw new Error(problem)
    if (!video.videoWidth || !video.videoHeight) throw new Error(strings.errors.cantDecode) // audio only
    signal.throwIfAborted()

    const { width, height } = fitSize(video.videoWidth, video.videoHeight, MAX_WIDTH)
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')
    if (!context) throw new Error(strings.errors.cantDecode)

    const times = frameTimes(video.duration, FPS)
    const encoded: Promise<ArrayBuffer>[] = []
    await captureFrames(
      video,
      times,
      (i) => {
        context.drawImage(video, 0, 0, width, height)
        encoded.push(encodeFrame(canvas))
        onProgress(i + 1, times.length)
      },
      signal,
    )
    const frames = await Promise.all(encoded)
    return { frames, durationS: video.duration, width, height }
  } finally {
    URL.revokeObjectURL(src)
    video.remove()
    video.removeAttribute('src')
    video.load() // releases the decoder
  }
}
