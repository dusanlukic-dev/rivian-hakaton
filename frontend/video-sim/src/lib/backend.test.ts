import { afterEach, describe, expect, it, vi } from 'vitest'
import { strings } from '@/strings'
import { backendLabel, getActiveTrip, getStatus, startTrip, toWsUrl } from './backend'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
afterEach(() => void vi.unstubAllGlobals())

describe('toWsUrl', () => {
  it('turns the http base into the camera socket url', () => {
    expect(toWsUrl('http://localhost:8000')).toBe('ws://localhost:8000/api/v1/camera/ws')
    expect(toWsUrl('https://abc.ngrok.app/')).toBe('wss://abc.ngrok.app/api/v1/camera/ws')
  })
  it('builds the live socket url', () => {
    expect(toWsUrl('http://localhost:5174', '/ws')).toBe('ws://localhost:5174/api/v1/ws')
  })
})

describe('getActiveTrip', () => {
  it('is the trip_id of the coordinator status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(200, { trip_id: 't1', camera: {} })))
    await expect(getActiveTrip()).resolves.toBe('t1')
  })
  it('is null without a trip', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(200, { trip_id: null })))
    await expect(getActiveTrip()).resolves.toBeNull()
  })
})

describe('getStatus', () => {
  it('reads /api/v1/coordinator/status', async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(200, { trip_id: null, camera: {} }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getStatus()).resolves.toMatchObject({ trip_id: null })
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/v1\/coordinator\/status$/)
  })
  it('says the backend is not reachable when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(getStatus()).rejects.toThrow(strings.errors.unreachable(backendLabel()))
  })
  it('says the same when the dev proxy answers 502', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 502 })))
    await expect(getStatus()).rejects.toThrow(strings.errors.unreachable(backendLabel()))
  })
})

describe('startTrip', () => {
  it('posts driver_id video-sim as JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(201, { trip_id: 't3' }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(startTrip()).resolves.toMatchObject({ trip_id: 't3' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/v1\/trips$/)
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({ 'content-type': 'application/json' })
    expect(JSON.parse(init.body)).toEqual({ driver_id: 'video-sim' })
  })
  it.each([
    [json(422, { detail: [{ msg: 'driver_id is required' }] }), 'driver_id is required'],
    [json(409, { detail: 'No active trip' }), 'No active trip'],
    [new Response('oops', { status: 500 }), 'HTTP 500'],
  ])('reports the backend detail (%#)', async (response, detail) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    await expect(startTrip()).rejects.toThrow(strings.errors.tripFailed(detail))
  })
  it('says the backend is not reachable when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(startTrip()).rejects.toThrow(strings.errors.unreachable(backendLabel()))
  })
})
