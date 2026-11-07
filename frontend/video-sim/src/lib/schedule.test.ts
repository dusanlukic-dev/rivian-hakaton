import { describe, expect, it, vi } from 'vitest'
import { FakeClock } from '@/test/fakeClock'
import { startSchedule } from './schedule'

function run(count: number) {
  const clock = new FakeClock()
  const frames: [number, number][] = []
  const onDone = vi.fn()
  const stop = startSchedule({ count, fps: 10, clock, onFrame: (i, s) => void frames.push([i, s]), onDone })
  return { clock, frames, onDone, stop }
}

describe('startSchedule', () => {
  it('sends frame 0 at once, then one every 100 ms, and ends at count × 100 ms', () => {
    const { clock, frames, onDone } = run(3)
    expect(frames).toEqual([[0, 0]])
    clock.advance(100)
    clock.advance(100)
    expect(frames).toEqual([[0, 0], [1, 0], [2, 0]])
    expect(onDone).not.toHaveBeenCalled()
    clock.advance(100)
    expect(onDone).toHaveBeenCalledTimes(1)
    expect(clock.pending).toBe(0)
  })
  it('jumps to the newest due frame after a late wake-up', () => {
    const { clock, frames } = run(10)
    clock.jumpTo(350)
    expect(frames).toEqual([[0, 0], [3, 2]])
    clock.advance(50)
    expect(frames.at(-1)).toEqual([4, 0])
  })
  it('ends right away when the last wake-up comes after the clip end', () => {
    const { clock, frames, onDone } = run(3)
    clock.jumpTo(1000)
    expect(frames).toEqual([[0, 0], [2, 1]])
    expect(onDone).toHaveBeenCalledTimes(1)
  })
  it('stop() cancels everything', () => {
    const { clock, frames, onDone, stop } = run(5)
    stop()
    clock.advance(1000)
    expect(frames).toEqual([[0, 0]])
    expect(onDone).not.toHaveBeenCalled()
    expect(clock.pending).toBe(0)
  })
})
