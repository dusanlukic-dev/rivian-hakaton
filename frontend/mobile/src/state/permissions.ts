import { AppState } from 'react-native';

import { getPermissionState, setupNotifications, type PermissionState } from '@/alerts/notifications';
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
      const before = permissionsStore.get().value;
      const value = await getPermissionState();
      permissionsStore.set({ value });
      // Android applies a channel's "bypass Do Not Disturb" only if the app has DND access when the channel is
      // submitted. Channels are re-submitted on every start (on the A54 `alarm_v1` went from mBypassDnd=false to
      // true on the first start after access was granted); re-submit right away too, without waiting for a restart.
      if (value.dnd && before?.dnd === false) {
        await setupNotifications().catch((e: unknown) => console.warn('[permissions] channels', e));
      }
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
