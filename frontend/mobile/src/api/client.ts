import { strings } from '@/config/strings';
import { authStore, signedOut } from '@/state/auth';
import { reportServer } from '@/state/server';
import { settingsStore } from '@/state/settings';

import { resolveMediaUrl, restBase, serverBase } from './address';
import { currentCarLink, type CarReply } from './carlink';
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

/** REST error. `status` 0 = network problem / timeout (car computer or server unreachable). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string | ValidationIssue[],
  ) {
    super(typeof detail === 'string' ? detail : detail.map((d) => d.msg).join(', ') || `HTTP ${status}`);
  }
}

/**
 * Where a call goes (docs/API.md §5): the car computer ([K]: live trip, start / end) or the server ([S]: accounts,
 * history, reports). They are separate programs with separate addresses.
 */
interface Target {
  kind: 'car' | 'server';
  /** As saved in settings, for messages. */
  address: string;
  base: string;
}

const car = (address: string): Target => ({ kind: 'car', address, base: restBase(address) });
const server = (address: string): Target => ({ kind: 'server', address, base: serverBase(address) });

/** A tunnel or proxy answering for a server that's down. Treated like no answer at all. */
const GATEWAY_DOWN = new Set([502, 504]);

/** Every call carries the login token when there is one. A 401 on it means the token is gone: log out. */
async function request<T>(target: Target, path: string, init: RequestInit = {}, timeoutMs = 5000): Promise<T> {
  const { address, kind } = target;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const token = authStore.get().token;
  let res: Response;
  try {
    res = await fetch(`${target.base}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        // a server behind a free ngrok tunnel would otherwise answer with ngrok's browser warning page
        ...(kind === 'server' ? { 'ngrok-skip-browser-warning': 'true' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      signal: controller.signal,
    });
  } catch {
    clearTimeout(timer);
    const timedOut = controller.signal.aborted;
    if (kind === 'server') {
      reportServer(address, false);
      throw new ApiError(0, timedOut ? strings.server.timedOut(address) : strings.server.unreachable(address));
    }
    throw new ApiError(
      0,
      timedOut
        ? `Timed out reaching ${address}. Is the car computer running?`
        : `Can't reach ${address}. Check the address and the network.`,
    );
  }
  try {
    if (kind === 'server') {
      const down = GATEWAY_DOWN.has(res.status);
      reportServer(address, !down);
      if (down) throw new ApiError(0, strings.server.unreachable(address));
    }
    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      if (res.status === 401 && token && authStore.get().token === token) signedOut();
      const detail = (body as { detail?: string | ValidationIssue[] } | null)?.detail;
      throw new ApiError(res.status, detail ?? `HTTP ${res.status}`);
    }
    return body as T;
  } finally {
    clearTimeout(timer);
  }
}

const post = (body?: unknown): RequestInit => ({ method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

const detailOf = (body: unknown) => (body as { detail?: string | ValidationIssue[] } | null)?.detail;

/**
 * A [K] call over the chosen car link: Bluetooth (docs/BLUETOOTH.md: the car's gateway makes the same REST call on
 * the car computer) or Wi-Fi/USB (`address`). Same errors either way: status 0 = the car can't be reached.
 */
async function carCall<T>(method: 'GET' | 'POST', path: string, body?: unknown, timeoutMs = 5000): Promise<T> {
  const { carLink, address } = settingsStore.get();
  if (carLink === 'wifi') return request<T>(car(address), path, method === 'POST' ? post(body) : {}, timeoutMs);
  const link = currentCarLink();
  if (!link) throw new ApiError(0, strings.carLink.notConnected);
  const token = authStore.get().token;
  let reply: CarReply;
  try {
    reply = await link.request(method, path, body, token, timeoutMs);
  } catch (e) {
    throw new ApiError(0, e instanceof Error && e.message ? e.message : strings.carLink.notConnected);
  }
  if (reply.status === 0) throw new ApiError(0, strings.carLink.carOffline);
  if (reply.status >= 400) {
    if (reply.status === 401 && token && authStore.get().token === token) signedOut();
    throw new ApiError(reply.status, detailOf(reply.body) ?? `HTTP ${reply.status}`);
  }
  return reply.body as T;
}

/** Image URLs in a report point at the server's media route: load them through the address this phone uses. */
function withMedia(serverAddress: string, report: TripReport): TripReport {
  return {
    ...report,
    sections: report.sections.map((s) => ({ ...s, image_url: resolveMediaUrl(serverAddress, s.image_url) })),
    moments: report.moments.map((m) => ({ ...m, image_url: resolveMediaUrl(serverAddress, m.image_url) })),
  };
}

/**
 * docs/API.md §5. Car calls [K] go over the chosen car link (settings `carLink`: Bluetooth or Wi-Fi); server calls [S]
 * take `serverAddress` (settings `serverAddress`: "host:port" or "https://host").
 */
export const api = {
  /** The car computer answers [K], over the chosen car link. */
  health: () => carCall<{ status: string }>('GET', '/health', undefined, 3000),
  /** One car computer address over Wi-Fi/USB, whatever the chosen link (Test on the car connection screen). */
  wifiHealth: (address: string) => request<{ status: string }>(car(address), '/health', {}, 3000),
  /** The server answers [S] (same route on both programs). */
  serverHealth: (serverAddress: string) => request<{ status: string }>(server(serverAddress), '/health', {}, 3000),

  register: (serverAddress: string, body: RegisterIn) =>
    request<AuthOut>(server(serverAddress), '/auth/register', post(body)),
  login: (serverAddress: string, body: LoginIn) => request<AuthOut>(server(serverAddress), '/auth/login', post(body)),
  logout: (serverAddress: string) => request<null>(server(serverAddress), '/auth/logout', post()),
  me: (serverAddress: string, timeoutMs?: number) => request<User>(server(serverAddress), '/auth/me', {}, timeoutMs),
  updateMe: (serverAddress: string, body: UserUpdate) =>
    request<User>(server(serverAddress), '/auth/me', { method: 'PATCH', body: JSON.stringify(body) }),

  /** Logged in: the trip belongs to the account (its username is the driver_id, its contact the default). */
  startTrip: (body: TripCreate = {}) => carCall<TripState>('POST', '/trips', body),
  /** Waits up to 3 s on the car computer for the server to get the whole trip, so allow more than usual. */
  endTrip: (tripId: string) => carCall<TripSummary>('POST', `/trips/${encodeURIComponent(tripId)}/end`, undefined, 10_000),
  getTrip: (tripId: string) => carCall<TripState>('GET', `/trips/${encodeURIComponent(tripId)}`),
  getSummary: (serverAddress: string, tripId: string) =>
    request<TripSummary>(server(serverAddress), `/trips/${encodeURIComponent(tripId)}/summary`),
  /** Logged in: my trips, oldest first. */
  listTrips: (serverAddress: string) => request<TripSummary[]>(server(serverAddress), '/trips'),
  /** The drive chart: summary + every 2 s section + dangerous moments with images. 503 = storage down → hide it. */
  getReport: async (serverAddress: string, tripId: string) =>
    withMedia(
      serverAddress,
      await request<TripReport>(server(serverAddress), `/trips/${encodeURIComponent(tripId)}/report`, {}, 10_000),
    ),
};
