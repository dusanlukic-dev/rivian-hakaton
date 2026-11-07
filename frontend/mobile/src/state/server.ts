import { createStore, useStore } from '@/lib/store';

/**
 * Whether the server (accounts, history, reports) answered the last call. 'unknown' until a call to the current
 * address resolves. Every server call reports here (`api/client.ts`), so screens get the state without polling.
 */
export type ServerStatus = 'unknown' | 'online' | 'offline';

export interface ServerState {
  status: ServerStatus;
  /** The server address `status` belongs to; a different saved address means 'unknown'. */
  address: string | null;
}

export const serverStore = createStore<ServerState>({ status: 'unknown', address: null });

/** Called by `api/client.ts` after every server call: answered (any HTTP status) or not. */
export function reportServer(address: string, reachable: boolean) {
  const status: ServerStatus = reachable ? 'online' : 'offline';
  const current = serverStore.get();
  if (current.address === address && current.status === status) return;
  serverStore.set({ address, status });
}

/** The status of `address`, 'unknown' when the last answer was about another address. */
export function useServerStatus(address: string): ServerStatus {
  return useStore(serverStore, (s) => (s.address === address ? s.status : 'unknown'));
}
