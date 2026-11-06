import { persist } from '@/lib/persist';
import { createStore, useStore } from '@/lib/store';

export interface Settings {
  /** "host:port" of the car computer (backend). */
  address: string;
  sound: boolean;
  vibration: boolean;
  flash: boolean;
  voice: boolean;
  keepAwake: boolean;
}

type SettingsState = Settings & { ready: boolean };

/** Works over USB with `adb reverse tcp:8000 tcp:8000`; on the hotspot use the laptop IP. */
export const DEFAULT_ADDRESS = 'localhost:8000';

export const settingsStore = createStore<SettingsState>({
  address: DEFAULT_ADDRESS,
  sound: true,
  vibration: true,
  flash: true,
  voice: true,
  keepAwake: true,
  ready: false,
});

export async function loadSettings() {
  await persist(settingsStore, 'settings.v1', ['address', 'sound', 'vibration', 'flash', 'voice', 'keepAwake']);
  settingsStore.set({ ready: true });
}

export function useSettings<S>(select: (state: SettingsState) => S): S {
  return useStore(settingsStore, select);
}
