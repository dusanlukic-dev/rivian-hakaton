import { restBase } from './address';
import type { ValidationIssue, TripCreate, TripState, TripSummary } from './types';

/** REST error. `status` 0 = network problem / timeout (car computer unreachable). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string | ValidationIssue[],
  ) {
    super(typeof detail === 'string' ? detail : detail.map((d) => d.msg).join(', ') || `HTTP ${status}`);
  }
}

async function request<T>(address: string, path: string, init: RequestInit = {}, timeoutMs = 5000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${restBase(address)}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      signal: controller.signal,
    });
    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      const detail = (body as { detail?: string | ValidationIssue[] } | null)?.detail;
      throw new ApiError(res.status, detail ?? `HTTP ${res.status}`);
    }
    return body as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(
      0,
      controller.signal.aborted
        ? `Timed out reaching ${address}. Is the car computer running?`
        : `Can't reach ${address}. Check the address and the network.`,
    );
  } finally {
    clearTimeout(timer);
  }
}

/** docs/API.md §5. `address` is "host:port" from the settings store. */
export const api = {
  health: (address: string) => request<{ status: string }>(address, '/health', {}, 3000),
  startTrip: (address: string, body: TripCreate) =>
    request<TripState>(address, '/trips', { method: 'POST', body: JSON.stringify(body) }),
  endTrip: (address: string, tripId: string) =>
    request<TripSummary>(address, `/trips/${encodeURIComponent(tripId)}/end`, { method: 'POST' }),
  getTrip: (address: string, tripId: string) => request<TripState>(address, `/trips/${encodeURIComponent(tripId)}`),
  getSummary: (address: string, tripId: string) =>
    request<TripSummary>(address, `/trips/${encodeURIComponent(tripId)}/summary`),
  listTrips: (address: string, driverId?: string) =>
    request<TripSummary[]>(address, driverId ? `/trips?driver_id=${encodeURIComponent(driverId)}` : '/trips'),
};
