import { DRIVER_ID } from '@/config'
import { strings } from '@/strings'

/** Every backend route is under this prefix (backend/app/core/config.py: api_prefix) */
export const API_PREFIX = '/api/v1'

/** '' in dev (same origin, the Vite proxy forwards /api), VITE_API_URL in a build (the backend allows CORS *) */
export function apiBase(): string {
  return import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL ?? '')
}

/** The backend address shown in messages */
export function backendLabel(): string {
  return import.meta.env.VITE_API_URL || 'http://localhost:8000'
}

/** http(s)://host[:port][/] → ws(s)://host[:port]/api/v1/camera/ws */
export function toWsUrl(httpBase: string): string {
  return `${httpBase.replace(/\/+$/, '').replace(/^http/, 'ws')}${API_PREFIX}/camera/ws`
}

/** The camera socket for this page: through the dev proxy, or straight to VITE_API_URL in a build */
export function cameraSocketUrl(): string {
  return toWsUrl(apiBase() || location.origin)
}

/** The part of GET /coordinator/status this site reads */
export interface CoordinatorStatus {
  trip_id: string | null
}

/** A network failure means the backend (or its address) is down */
async function request(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${apiBase()}${API_PREFIX}${path}`, init)
  } catch {
    throw new Error(strings.errors.unreachable(backendLabel()))
  }
}

/** Any error status counts as unreachable too: with the backend down, the dev proxy answers 5xx itself */
export async function getStatus(): Promise<CoordinatorStatus> {
  const response = await request('/coordinator/status')
  if (!response.ok) throw new Error(strings.errors.unreachable(backendLabel()))
  return (await response.json()) as CoordinatorStatus
}

/** POST /trips without a login. It ends any trip in progress, so call it only when none is active (ensureTrip) */
export async function startTrip(): Promise<{ trip_id: string }> {
  const response = await request('/trips', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ driver_id: DRIVER_ID }),
  })
  if (!response.ok) throw new Error(strings.errors.tripFailed(await errorDetail(response)))
  return (await response.json()) as { trip_id: string }
}

/** FastAPI's `detail`: a string, or validation errors whose first `msg` is shown */
async function errorDetail(response: Response): Promise<string> {
  try {
    const { detail } = (await response.json()) as { detail?: unknown }
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') return detail[0].msg
  } catch {
    // not JSON
  }
  return `HTTP ${response.status}`
}

export interface TripApi {
  getStatus(): Promise<CoordinatorStatus>
  startTrip(): Promise<{ trip_id: string }>
}

/** The backend drops camera frames without an active trip: use the one in progress, or start one if there is none */
export async function ensureTrip(api: TripApi = { getStatus, startTrip }): Promise<{ tripId: string; started: boolean }> {
  const status = await api.getStatus()
  if (status.trip_id) return { tripId: status.trip_id, started: false }
  const trip = await api.startTrip()
  return { tripId: trip.trip_id, started: true }
}
