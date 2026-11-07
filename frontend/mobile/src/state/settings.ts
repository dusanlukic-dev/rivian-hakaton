import { persist } from '@/lib/persist';
import { createStore, useStore } from '@/lib/store';

export interface Settings {
  /** "host:port" of the car computer (backend). */
  address: string;
  /**
   * The server (accounts, history, drive reports), as `normalizeServerAddress` saves it: "host:port" for plain http,
   * "https://host[:port]" for a secure link (e.g. an ngrok tunnel).
   */
  serverAddress: string;
  sound: boolean;
  vibration: boolean;
  flash: boolean;
  voice: boolean;
  keepAwake: boolean;
}

/** The on/off alert preferences (Settings → Alerts). */
export type AlertToggle = 'sound' | 'vibration' | 'flash' | 'voice' | 'keepAwake';

type SettingsState = Settings & { ready: boolean };

/** Works over USB with `adb reverse tcp:8000 tcp:8000`; on the hotspot use the laptop IP. */
export const DEFAULT_ADDRESS = 'localhost:8000';

/** The server over USB: `adb reverse tcp:8001 tcp:8001`. On the hotspot use the laptop IP, or a tunnel's https link. */
export const DEFAULT_SERVER_ADDRESS = 'localhost:8001';

export const settingsStore = createStore<SettingsState>({
  address: DEFAULT_ADDRESS,
  serverAddress: DEFAULT_SERVER_ADDRESS,
  sound: true,
  vibration: true,
  flash: true,
  voice: true,
  keepAwake: true,
  ready: false,
});

export async function loadSettings() {
  await persist(settingsStore, 'settings.v1', ['address', 'serverAddress', 'sound', 'vibration', 'flash', 'voice', 'keepAwake']);
  settingsStore.set({ ready: true });
}

export function useSettings<S>(select: (state: SettingsState) => S): S {
  return useStore(settingsStore, select);
}
