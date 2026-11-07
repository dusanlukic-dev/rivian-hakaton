import type { Clock } from '@/lib/schedule'

interface Timer {
  id: number
  at: number
  fn: () => void
}

/** Test clock: time only moves when the test says so */
export class FakeClock implements Clock {
  /** Current time in ms */
  t = 0
  private timers: Timer[] = []
  private nextId = 1

  get pending(): number {
    return this.timers.length
  }

  now(): number {
    return this.t
  }

  setTimeout(fn: () => void, ms: number): number {
    const id = this.nextId++
    this.timers.push({ id, at: this.t + Math.max(0, ms), fn })
    return id
  }

  clearTimeout(handle: unknown): void {
    this.timers = this.timers.filter((timer) => timer.id !== handle)
  }

  /** Runs every timer that comes due up to t + ms, each at its own time, then sets t = t + ms */
  advance(ms: number): void {
    const end = this.t + ms
    for (let timer = this.takeDue(end); timer; timer = this.takeDue(end)) {
      this.t = Math.max(this.t, timer.at)
      timer.fn()
    }
    this.t = end
  }

  /** A late wake-up: t jumps to `target` first, then the timers due by then run, all seeing now() = target */
  jumpTo(target: number): void {
    this.t = target
    for (let timer = this.takeDue(target); timer; timer = this.takeDue(target)) timer.fn()
  }

  /** Removes and returns the earliest timer due by `limit` (on a tie, the one set first) */
  private takeDue(limit: number): Timer | undefined {
    let first: Timer | undefined
    for (const timer of this.timers) if (timer.at <= limit && (!first || timer.at < first.at)) first = timer
    if (first) this.timers = this.timers.filter((timer) => timer !== first)
    return first
  }
}
