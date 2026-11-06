import axios from 'axios'
import api from '@/utils/api/client'
import type { ApiError, Behavior, TripCreate, TripReport, TripState, TripSummary } from '@/api/types'

/** Every route in docs/API.md is relative to this */
export const API_PREFIX = '/api/v1'

export const startTrip = (body: TripCreate) =>
  api.post<TripState>(`${API_PREFIX}/trips`, body).then((r) => r.data)

export const endTrip = (tripId: string) =>
  api.post<TripSummary>(`${API_PREFIX}/trips/${tripId}/end`).then((r) => r.data)

/** The drive chart: every 2 s section + the dangerous moments with images. 503 = storage down, 404 = not stored */
export const getReport = (tripId: string) =>
  api.get<TripReport>(`${API_PREFIX}/trips/${tripId}/report`).then((r) => r.data)

/** One camera sample (`TelemetryTick` in backend/app/schemas/trip.py). Normally sent by the camera models, not the UI */
export interface TelemetryTick {
  /** Local time WITH the UTC offset (night penalty uses the local hour), see `localIsoTimestamp` */
  timestamp: string
  speed_kmh: number
  behaviors: Behavior[]
}

/** 409 = no active trip */
export const postTelemetry = (tick: TelemetryTick) => api.post<TripState>(`${API_PREFIX}/telemetry`, tick).then((r) => r.data)

/** e.g. `2026-11-06T22:15:03.120+01:00` (toISOString() would give UTC with `Z`) */
export function localIsoTimestamp(date = new Date()): string {
  const pad = (n: number, width = 2) => String(n).padStart(width, '0')
  const offset = -date.getTimezoneOffset()
  const sign = offset >= 0 ? '+' : '-'
  const abs = Math.abs(offset)
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${pad(date.getMilliseconds(), 3)}` +
    `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
  )
}

export const httpStatus = (error: unknown) => (axios.isAxiosError(error) ? error.response?.status : undefined)

/** `detail` for 404/409, the first validation message for 422, else the transport error */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError<ApiError>(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]) return detail[0].msg
    return error.message
  }
  return error instanceof Error ? error.message : String(error)
}
