import * as Brightness from 'expo-brightness';
import { AppState, Vibration } from 'react-native';

import type { SafetyLevel, TripState } from '@/api/types';
import { ackEmergency, liveStore } from '@/state/live';
import { settingsStore } from '@/state/settings';

import * as notify from './notifications';
import { textEmergencyContact } from './sms';
import { sounds } from './sounds';

/**
 * Executes the backend's `response` (docs/API.md §7): never decides levels itself.
 * Haptics/notifications live here; the red flash + emergency screen are in components/AlertOverlays.
 * Sound follows the level, not the backend's `response.sound` (which is loud from orange up), and there is no
 * spoken voice (D53):
 * - yellow (`warning`) and orange (`high_risk`): no sound, only vibration, the red pulse and the silent heads-up;
 * - red (`critical`, and the `emergency` level once the driver has dismissed the emergency): the calm bell, only
 *   while something risky is happening now (`response.sound` is not `none`), so it stops when the phone goes away;
 * - the emergency event: the stronger bell, looped until the driver taps "I'm OK", and a text to the emergency
 *   contact, sent by the phone itself (alerts/sms.ts, D54).
 */
const RANK: Record<SafetyLevel, number> = { safe: 0, caution: 1, warning: 2, high_risk: 3, critical: 4, emergency: 5 };

let started = false;
let lastTick = 0;
let lastBackgroundWarningAt = 0;
let emergencyOn = false;
let driveServiceOn = false;

function onTick(trip: TripState) {
  const prefs = settingsStore.get();
  const { response } = trip;
  const now = Date.now();

  if (prefs.vibration && response.vibrate_seat) Vibration.vibrate(350);
  if (prefs.sound && RANK[trip.level] >= RANK.critical && response.sound !== 'none') sounds.play('critical');

  // Silent heads-up while the app is in the background (no sound: see the channel in notifications.ts).
  if (response.sound === 'high' && AppState.currentState !== 'active' && now - lastBackgroundWarningAt > 10_000) {
    lastBackgroundWarningAt = now;
    void notify.showWarning(response.message);
  }
}

function startEmergency(state: TripState) {
  void textEmergencyContact(state); // first: the text must not wait for sounds or the screen
  const prefs = settingsStore.get();
  sounds.stop('critical');
  if (prefs.sound) sounds.loop('siren');
  if (prefs.vibration) Vibration.vibrate([0, 700, 300], true);
  Brightness.setBrightnessAsync(1).catch(() => {});
  if (AppState.currentState !== 'active') void notify.showEmergency(state);
}

function stopEmergency() {
  sounds.stop('siren');
  Vibration.cancel();
  Brightness.restoreSystemBrightnessAsync().catch(() => {});
  void notify.cancelEmergency();
}

export function startAlertEngine() {
  if (started) return;
  started = true;
  lastTick = liveStore.get().tick;

  liveStore.subscribe(() => {
    const s = liveStore.get();

    if (s.tick !== lastTick) {
      lastTick = s.tick;
      const shown = s.preview ?? s.trip; // a running test alert plays instead of the live trip
      if (shown && !emergencyOn) onTick(shown);
    }

    if ((s.emergency !== null) !== emergencyOn) {
      emergencyOn = s.emergency !== null;
      if (s.emergency) startEmergency(s.emergency);
      else stopEmergency();
    }

    const wantService = s.trip !== null; // real trips only: test alerts live in `preview`
    if (wantService !== driveServiceOn) {
      driveServiceOn = wantService;
      void (wantService ? notify.startDriveService() : notify.stopDriveService());
    }
  });

  // Emergency while backgrounded → insistent full-screen notification; back in the app → the overlay takes over.
  AppState.addEventListener('change', (state) => {
    const { emergency } = liveStore.get();
    if (!emergency) return;
    if (state === 'active') void notify.cancelEmergency();
    else void notify.showEmergency(emergency);
  });

  notify.onNotificationAction((actionId) => {
    if (actionId === 'ack') ackEmergency();
  });
}
