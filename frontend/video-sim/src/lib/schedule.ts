/** The time source of the schedule: performance.now() + timers in the worker, FakeClock in tests */
export interface Clock {
  /** Milliseconds, monotonic */
  now(): number
  setTimeout(fn: () => void, ms: number): unknown
  clearTimeout(handle: unknown): void
}

export interface ScheduleOptions {
  count: number
  fps: number
  clock: Clock
  /** Frame `index` is due now. `skippedBefore` frames before it were due as well and are dropped (late wake-up) */
  onFrame(index: number, skippedBefore: number): void
  /** At t0 + count × 1000 / fps: the clip is over */
  onDone(): void
}

/**
 * Real time, like a camera: frame i is due at t0 + i × 1000 / fps, never earlier. A late wake-up sends only the
 * newest due frame (the backend's model also takes only the newest), so the stream never falls behind the clock.
 * Returns stop().
 */
export function startSchedule({ count, fps, clock, onFrame, onDone }: ScheduleOptions): () => void {
  const interval = 1000 / fps
  const t0 = clock.now()
  let next = 0 // the first frame neither sent nor skipped yet
  let timer: unknown = null
  let stopped = false

  const wake = () => {
    timer = null
    const elapsed = clock.now() - t0
    // Frames whose time has come; the epsilon keeps a wake-up exactly on time from landing one frame short
    const due = Math.min(count, Math.floor(elapsed / interval + 1e-9) + 1)
    if (due > next) {
      onFrame(due - 1, due - 1 - next)
      next = due
    }
    if (stopped) return // onFrame may have stopped the schedule
    const at = next === count ? count * interval : next * interval
    if (next === count && elapsed >= at) {
      onDone()
      return
    }
    timer = clock.setTimeout(wake, at - elapsed)
  }

  wake()
  return () => {
    stopped = true
    if (timer !== null) clock.clearTimeout(timer)
    timer = null
  }
}
