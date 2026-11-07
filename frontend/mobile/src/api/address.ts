export const DEFAULT_PORT = 8000;

/**
 * Normalises whatever the user typed or scanned into "host:port".
 * Accepts "10.0.0.5", "10.0.0.5:8000", "http://10.0.0.5:8000/api/v1", "ws://10.0.0.5:8000/api/v1/ws".
 * Returns null when nothing usable is left.
 */
export function normalizeAddress(input: string): string | null {
  let s = input.trim();
  if (!s) return null;
  s = s.replace(/^[a-z]+:\/\//i, '');
  s = s.split(/[/?#]/)[0] ?? '';
  if (!s) return null;
  if (!/:\d+$/.test(s)) s = `${s}:${DEFAULT_PORT}`;
  return /^[\w.-]+:\d{1,5}$/.test(s) ? s : null;
}

export const restBase = (address: string) => `http://${address}/api/v1`;
export const wsUrl = (address: string) => `ws://${address}/api/v1/ws`;

// ---------- Server (accounts, history, reports: the [S] routes of docs/API.md §5) ----------

export const DEFAULT_SERVER_PORT = 8001;

const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/;

/**
 * Normalises the server address into its saved form, which is also what the app shows:
 * "host:port" for plain http (the laptop over the hotspot, localhost over USB) and "https://host[:port]" for a
 * secure link (a tunnel such as ngrok). Accepts "10.0.0.5", "10.0.0.5:8001", "http://10.0.0.5:8001/api/v1",
 * "https://abc.ngrok-free.app/api/v1" and "abc.ngrok-free.app".
 * Without a scheme, an IP or localhost gets http and port 8001, and a domain name without a port gets https.
 * With a scheme, a missing port means the scheme's own (80 / 443). Returns null when nothing usable is left.
 */
export function normalizeServerAddress(input: string): string | null {
  const trimmed = input.trim();
  if (!trimmed) return null;
  const scheme = /^([a-z][a-z0-9+.-]*):\/\//i.exec(trimmed)?.[1]?.toLowerCase();
  if (scheme !== undefined && scheme !== 'http' && scheme !== 'https') return null;
  const hostPort = trimmed.replace(/^[a-z][a-z0-9+.-]*:\/\//i, '').split(/[/?#]/)[0] ?? '';
  const match = /^([\w.-]+)(?::(\d{1,5}))?$/.exec(hostPort);
  if (!match) return null;
  const host = match[1].toLowerCase();
  const port = match[2] === undefined ? null : Number(match[2]);
  if (port !== null && (port < 1 || port > 65535)) return null;
  const local = host === 'localhost' || IPV4.test(host);
  const secure = scheme === 'https' || (scheme === undefined && port === null && !local);
  if (secure) return port === null ? `https://${host}` : `https://${host}:${port}`;
  return `${host}:${port ?? (scheme === 'http' ? 80 : DEFAULT_SERVER_PORT)}`;
}

/** "http://10.0.0.5:8001" / "https://abc.ngrok-free.app" for a saved server address. */
export const serverOrigin = (address: string) => (/^https:\/\//i.test(address) ? address : `http://${address}`);
export const serverBase = (address: string) => `${serverOrigin(address)}/api/v1`;

const MEDIA_PATH = /\/api\/v1\/media\/.+$/;

/**
 * Report images come back as absolute URLs on the address the server saw (FastAPI `url_for`). Behind a tunnel or a
 * proxy that can differ from the address the phone uses, so anything on the media route (or relative) is re-based
 * onto the phone's server address. Other absolute URLs (signed storage links, later) stay as they are.
 */
export function resolveMediaUrl(address: string, url: string | null): string | null {
  if (!url) return url;
  const path = MEDIA_PATH.exec(url)?.[0];
  if (path) return `${serverOrigin(address)}${path}`;
  return url.startsWith('/') ? `${serverOrigin(address)}${url}` : url;
}

// ---------- The car screen's QR code / deep link ----------

/** Same scheme as app.json `scheme`. The car screen's Connect phone card encodes this link. */
const CONNECT_LINK = /^driveralert:\/\/connect\/?\?(.*)$/i;

export interface ConnectLink {
  /** The server's address (`serverAddress` in settings). */
  serverAddress?: string;
  /** The car computer's address (`address` in settings). */
  address?: string;
}

function queryParams(query: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of query.split('&')) {
    const [key, value = ''] = part.split('=');
    if (!key) continue;
    try {
      out[decodeURIComponent(key)] = decodeURIComponent(value.replace(/\+/g, ' '));
    } catch {
      // malformed escape: skip this pair
    }
  }
  return out;
}

/** `server` / `car` from the link (deep link params arrive already split). Null when neither is usable. */
export function connectFromParams(server: string | undefined, car: string | undefined): ConnectLink | null {
  const serverAddress = server ? normalizeServerAddress(server) : null;
  const address = car ? normalizeAddress(car) : null;
  if (!serverAddress && !address) return null;
  return { ...(serverAddress ? { serverAddress } : {}), ...(address ? { address } : {}) };
}

/**
 * Reads what the car screen's QR code carries: `driveralert://connect?server=<host:port>&car=<host:port>`.
 * A bare address (the older QR code) is the car computer's. Null when nothing usable is in it.
 */
export function parseConnectLink(data: string): ConnectLink | null {
  const link = CONNECT_LINK.exec(data.trim());
  if (link) {
    const params = queryParams(link[1] ?? '');
    return connectFromParams(params.server, params.car);
  }
  const address = normalizeAddress(data);
  return address ? { address } : null;
}
