/** Frames per second sent to the backend: its video cache keeps at most 10/s (VIDEO_CACHE_FPS) */
export const FPS = 10
/** Frames wider than this are scaled down (same aspect ratio, never up) */
export const MAX_WIDTH = 1280
export const JPEG_QUALITY = 0.8
/** Second try for a frame still larger than MAX_FRAME_BYTES */
export const FALLBACK_QUALITY = 0.5
/** Longer clips are refused: every frame is held in memory before sending (30 s ≈ 50 MB) */
export const MAX_DURATION_S = 120
/** The backend drops larger camera frames (MAX_FRAME_BYTES in backend/app/coordinator/routes/live.py) */
export const MAX_FRAME_BYTES = 2_000_000
/** A frame is skipped while the socket still holds this much unsent data (the newest frame wins) */
export const MAX_BUFFERED_BYTES = 1_000_000
/** The worker reports progress at most this often */
export const PROGRESS_EVERY_MS = 250
/** Trips this site starts (Send when no fresh trip is active) belong to this driver, not to an account */
export const DRIVER_ID = 'video-sim'
/**
 * The coordinator takes one camera and refuses a second socket. Right after a send stops (Stop, or the phone started a
 * new trip mid-clip) the old socket may still count on its side, so a socket refused before it opened is retried
 */
export const CONNECT_ATTEMPTS = 6
export const CONNECT_RETRY_MS = 400
/** Reconnect delay of the trip-events socket (WS /api/v1/ws) after it closes */
export const LIVE_RETRY_MS = 2000
