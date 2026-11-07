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

/** http(s)://host[:port][/] → ws(s)://host[:port]/api/v1<path> (default: the camera socket) */
export function toWsUrl(httpBase: string, path = '/camera/ws'): string {
  return `${httpBase.replace(/\/+$/, '').replace(/^http/, 'ws')}${API_PREFIX}${path}`
}

/** The camera socket for this page: through the dev proxy, or straight to VITE_API_URL in a build */
export function cameraSocketUrl(): string {
  return toWsUrl(apiBase() || location.origin)
}

/** The live socket the phone and the dashboard listen to: this page only reads trip_started / trip_ended from it */
export function liveSocketUrl(): string {
  return toWsUrl(apiBase() || location.origin, '/ws')
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

/** The trip the coordinator runs now, or null */
export async function getActiveTrip(): Promise<string | null> {
  return (await getStatus()).trip_id
}

/** POST /trips without a login: a new trip for driver video-sim. It ends the trip in progress, if any */
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
