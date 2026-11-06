import type { AuthOut, User } from '@/api/types';
import { persist } from '@/lib/persist';
import { createStore, useStore } from '@/lib/store';

/**
 * The driver's account (docs/API.md §5, /auth/*). The token rides on every REST call (`api/client.ts`); a 401 drops
 * it, and the root layout then shows the login screen. Trips started while logged in belong to the account.
 */
export interface AuthState {
  token: string | null;
  user: User | null;
  /** Loaded from storage. Until then the app renders nothing, so the login screen never flashes. */
  ready: boolean;
}

export const authStore = createStore<AuthState>({ token: null, user: null, ready: false });

export async function loadAuth() {
  await persist(authStore, 'auth.v1', ['token', 'user']);
  authStore.set({ ready: true });
}

export function signedIn(out: AuthOut) {
  authStore.set({ token: out.token, user: out.user });
}

export function setUser(user: User) {
  authStore.set({ user });
}

export function signedOut() {
  authStore.set({ token: null, user: null });
}

export function useAuth<S>(select: (state: AuthState) => S): S {
  return useStore(authStore, select);
}
