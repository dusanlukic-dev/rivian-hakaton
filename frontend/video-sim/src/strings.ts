/** Every user-facing string (English, like the dashboard and the phone app) lives here */
export const strings = {
  title: 'Video sim',
  subtitle: 'Plays a recorded clip as the in-cabin camera: frames go to the backend in real time.',
  drop: 'Drop a video here or click to choose',
  preparing: (done: number, total: number) => `Preparing frames ${done} / ${total}`,
  clipInfo: (frames: number, seconds: number, width: number, height: number) =>
    `${frames} frames · ${seconds.toFixed(1)} s · ${width}×${height}`,
  send: 'Send',
  stop: 'Stop',
  chooseAnother: 'Choose another',
  checkingTrip: 'Checking trip…',
  progress: (sentS: number, totalS: number) => `${sentS.toFixed(1)} / ${totalS.toFixed(1)} s`,
  startedTrip: 'Started trip video-sim',
  activeTrip: 'Sending into the active trip',
  sentSummary: (sent: number, skipped: number) => `Sent ${sent} frames, ${skipped} skipped`,
  errors: {
    notVideo: 'That file is not a video.',
    cantDecode: "This browser can't decode the video. Export it as MP4 (H.264).",
    tooLong: 'The clip is longer than 2 minutes. Trim it first.',
    frameTooBig: 'A frame is still larger than 2 MB. Use a smaller video.',
    unreachable: (base: string) => `Backend not reachable at ${base}. Start it with python run.py.`,
    tripFailed: (detail: string) => `Couldn't start a trip: ${detail}`,
    lost: (seconds: number) => `Lost the connection to the backend after ${seconds.toFixed(1)} s.`,
    cantConnect: "Couldn't connect to the backend camera socket.",
    senderCrashed: 'The sender stopped unexpectedly.',
  },
}
