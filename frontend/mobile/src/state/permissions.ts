import { AppState } from 'react-native';

import { getPermissionState, type PermissionState } from '@/alerts/notifications';
import { createStore, useStore } from '@/lib/store';

interface PermissionsState {
  /** null until the first check (or if Android refused to answer). */
  value: PermissionState | null;
  checking: boolean;
}

export const permissionsStore = createStore<PermissionsState>({ value: null, checking: false });

export function usePermissions<S>(select: (state: PermissionsState) => S): S {
  return useStore(permissionsStore, select);
}

let pending: Promise<void> | null = null;

/** Re-reads what Android currently allows. Concurrent calls share one check. */
export function refreshPermissions(): Promise<void> {
  pending ??= (async () => {
    permissionsStore.set({ checking: true });
    try {
      permissionsStore.set({ value: await getPermissionState() });
    } catch (e) {
      console.warn('[permissions] check failed', e);
    } finally {
      permissionsStore.set({ checking: false });
      pending = null;
    }
  })();
  return pending;
}

let watching = false;

/**
 * Permissions are granted in Android's own settings screens, so the app only finds out when it comes back
 * to the foreground (that isn't a navigation focus change). Starts once, for the whole app.
 */
export function watchPermissions() {
  if (watching) return;
  watching = true;
  AppState.addEventListener('change', (state) => {
    if (state === 'active') void refreshPermissions();
  });
}
