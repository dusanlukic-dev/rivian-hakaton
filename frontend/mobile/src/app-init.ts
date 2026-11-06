import { startAlertEngine } from '@/alerts/engine';
import { setupNotifications } from '@/alerts/notifications';
import { initSounds } from '@/alerts/sounds';
import { loadAuth } from '@/state/auth';
import { startLive } from '@/state/live';
import { loadSettings } from '@/state/settings';

let started = false;

/** Boots stores, audio, notification channels, the live socket and the alert engine (once per app process). */
export function initApp() {
  if (started) return;
  started = true;
  void (async () => {
    await Promise.all([loadSettings(), loadAuth()]);
    await initSounds();
    await setupNotifications().catch((e) => console.warn('[init] notification channels', e));
    startLive();
    startAlertEngine();
  })();
}
