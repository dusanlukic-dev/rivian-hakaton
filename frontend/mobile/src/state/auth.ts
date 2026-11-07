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
  /**
   * The boot check is done (app-init.ts): the saved session was read and, if there is one, checked with the server.
   * Until then the native splash screen stays up, so neither the login screen nor stale account data ever flash.
   */
  ready: boolean;
  /** The server confirmed the token in this app run. False = offline start with the saved session (checked later). */
  verified: boolean;
}

export const authStore = createStore<AuthState>({ token: null, user: null, ready: false, verified: false });

/** Reads the saved session from storage. `ready` is set by the boot check, not here. */
export function loadAuth() {
  return persist(authStore, 'auth.v1', ['token', 'user']);
}

export function signedIn(out: AuthOut) {
  authStore.set({ token: out.token, user: out.user, verified: true });
}

export function setUser(user: User) {
  authStore.set({ user, verified: true });
}

export function signedOut() {
  authStore.set({ token: null, user: null, verified: false });
}

export function useAuth<S>(select: (state: AuthState) => S): S {
  return useStore(authStore, select);
}
