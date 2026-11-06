import { authStore, signedOut } from '@/state/auth';

import { restBase } from './address';
import type {
  AuthOut,
  LoginIn,
  RegisterIn,
  TripCreate,
  TripReport,
  TripState,
  TripSummary,
  User,
  UserUpdate,
  ValidationIssue,
} from './types';

/** REST error. `status` 0 = network problem / timeout (car computer unreachable). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string | ValidationIssue[],
  ) {
    super(typeof detail === 'string' ? detail : detail.map((d) => d.msg).join(', ') || `HTTP ${status}`);
  }
}

/** Every call carries the login token when there is one. A 401 on it means the token is gone: log out. */
async function request<T>(address: string, path: string, init: RequestInit = {}, timeoutMs = 5000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const token = authStore.get().token;
  try {
    const res = await fetch(`${restBase(address)}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      signal: controller.signal,
    });
    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      if (res.status === 401 && token && authStore.get().token === token) signedOut();
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

const post = (body?: unknown): RequestInit => ({ method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

/** docs/API.md §5. `address` is "host:port" from the settings store. */
export const api = {
  health: (address: string) => request<{ status: string }>(address, '/health', {}, 3000),

  register: (address: string, body: RegisterIn) => request<AuthOut>(address, '/auth/register', post(body)),
  login: (address: string, body: LoginIn) => request<AuthOut>(address, '/auth/login', post(body)),
  logout: (address: string) => request<null>(address, '/auth/logout', post()),
  me: (address: string) => request<User>(address, '/auth/me'),
  updateMe: (address: string, body: UserUpdate) =>
    request<User>(address, '/auth/me', { method: 'PATCH', body: JSON.stringify(body) }),

  /** Logged in: the trip belongs to the account (its username is the driver_id, its contact the default). */
  startTrip: (address: string, body: TripCreate = {}) => request<TripState>(address, '/trips', post(body)),
  endTrip: (address: string, tripId: string) =>
    request<TripSummary>(address, `/trips/${encodeURIComponent(tripId)}/end`, post()),
  getTrip: (address: string, tripId: string) => request<TripState>(address, `/trips/${encodeURIComponent(tripId)}`),
  getSummary: (address: string, tripId: string) =>
    request<TripSummary>(address, `/trips/${encodeURIComponent(tripId)}/summary`),
  /** Logged in: my trips, oldest first. */
  listTrips: (address: string) => request<TripSummary[]>(address, '/trips'),
  /** The drive chart: summary + every 2 s section + dangerous moments with images. 503 = storage down → hide it. */
  getReport: (address: string, tripId: string) =>
    request<TripReport>(address, `/trips/${encodeURIComponent(tripId)}/report`, {}, 10_000),
};
