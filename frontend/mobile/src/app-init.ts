import { startAlertEngine } from '@/alerts/engine';
import { setupNotifications } from '@/alerts/notifications';
import { initSounds } from '@/alerts/sounds';
import { api } from '@/api/client';
import { authStore, loadAuth, setUser } from '@/state/auth';
import { liveStore, startLive, waitForLink } from '@/state/live';
import { refreshPermissions } from '@/state/permissions';
import { loadSettings, settingsStore } from '@/state/settings';

/** How long the boot check may ask the server whether the saved login is still valid. */
const SESSION_CHECK_MS = 2500;
/** How long the boot check waits for the car computer's first answer, so the Drive tab opens in its real state. */
const LINK_WAIT_MS = 1500;
/** Hard limit: the splash screen never stays up longer than this, whatever happens. */
const BOOT_LIMIT_MS = 4000;

let started = false;

/**
 * Boots the app once per process. The native splash stays up (root layout) until `authStore.ready`:
 * saved settings + session are read, the live socket starts, and the saved session is checked with the server.
 * Only then does the first screen render, already in its final state: no login-screen flash, no stale name,
 * no "offline" card that turns into "ready" half a second later.
 */
export function initApp() {
  if (started) return;
  started = true;
  const failSafe = setTimeout(markReady, BOOT_LIMIT_MS);
  void (async () => {
    try {
      await Promise.all([loadSettings(), loadAuth()]);
      startLive();
      void startAlerts(); // sounds, channels, alert engine: needed only once a trip runs, don't hold the splash
      void refreshPermissions(); // so Settings → Phone setup opens with its real state
      await Promise.all([checkSession(SESSION_CHECK_MS), waitForLink(LINK_WAIT_MS)]);
    } catch (e) {
      console.warn('[init] boot', e);
    } finally {
      clearTimeout(failSafe);
      markReady();
    }
    recheckSessionWhenOnline();
  })();
}

function markReady() {
  if (!authStore.get().ready) authStore.set({ ready: true });
}

async function startAlerts() {
  await initSounds();
  await setupNotifications().catch((e: unknown) => console.warn('[init] notification channels', e));
  startAlertEngine();
}

/**
 * Asks the server whether the saved token is still valid (and gets fresh account data). A 401 logs out inside
 * `api/client.ts`, so the guard shows the login screen. Unreachable: the saved session stays (the car computer may
 * simply be off) and is checked again as soon as the car answers.
 */
async function checkSession(timeoutMs?: number) {
  if (!authStore.get().token) return;
  try {
    setUser(await api.me(settingsStore.get().address, timeoutMs));
  } catch {
    // offline start: keep the saved session for now
  }
}

function recheckSessionWhenOnline() {
  let last = liveStore.get().link;
  liveStore.subscribe(() => {
    const { link } = liveStore.get();
    if (link === last) return;
    last = link;
    const { token, verified } = authStore.get();
    if (link === 'online' && token && !verified) void checkSession();
  });
}
