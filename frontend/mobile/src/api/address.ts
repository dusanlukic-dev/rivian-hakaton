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
