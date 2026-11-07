import { describe, expect, it } from 'vitest'
import { strings } from '@/strings'
import { durationError, fitSize, frameTimes } from './frames'

describe('frameTimes', () => {
  it('gives floor(duration × fps) frames, 0.1 s apart at 10 fps', () => {
    const t = frameTimes(30, 10)
    expect(t).toHaveLength(300)
    expect(t[0]).toBe(0)
    expect(t[1]).toBeCloseTo(0.1)
    expect(t[299]).toBeCloseTo(29.9)
  })
  it('ignores a fraction of a frame at the end', () => expect(frameTimes(30.04, 10)).toHaveLength(300))
  it('always gives at least one frame', () => expect(frameTimes(0.05, 10)).toEqual([0]))
})

describe('fitSize', () => {
  it('scales a 1080p clip down to 1280×720', () => expect(fitSize(1920, 1080, 1280)).toEqual({ width: 1280, height: 720 }))
  it('never scales up', () => expect(fitSize(640, 480, 1280)).toEqual({ width: 640, height: 480 }))
  it('rounds to whole pixels', () => expect(fitSize(1001, 563, 1000)).toEqual({ width: 1000, height: 562 }))
})

describe('durationError', () => {
  it('accepts clips up to 2 minutes', () => {
    expect(durationError(30)).toBeNull()
    expect(durationError(120)).toBeNull()
  })
  it('rejects a longer clip', () => expect(durationError(120.5)).toBe(strings.errors.tooLong))
  it('rejects an unknown or empty duration', () => {
    for (const d of [Infinity, Number.NaN, 0]) expect(durationError(d)).toBe(strings.errors.cantDecode)
  })
})
