import * as Brightness from 'expo-brightness';
import * as Speech from 'expo-speech';
import { AppState, Vibration } from 'react-native';

import type { SafetyLevel, TripState } from '@/api/types';
import { isCollapse } from '@/config/behaviors';
import { strings } from '@/config/strings';
import { ackEmergency, liveStore } from '@/state/live';
import { settingsStore } from '@/state/settings';

import * as notify from './notifications';
import { sounds } from './sounds';

/**
 * Executes the backend's `response` (docs/API.md §7): never decides levels itself.
 * Audio/haptics/voice/notifications live here; the red flash + emergency screen are in components/AlertOverlays.
 */
const RANK: Record<SafetyLevel, number> = { safe: 0, caution: 1, warning: 2, high_risk: 3, critical: 4, emergency: 5 };

let started = false;
let lastTick = 0;
let lastLevel: SafetyLevel = 'safe';
let lastSpokenAt = 0;
let lastBackgroundWarningAt = 0;
let emergencyOn = false;
let driveServiceOn = false;

function onTick(trip: TripState) {
  const prefs = settingsStore.get();
  const { response } = trip;
  const now = Date.now();

  if (prefs.vibration && response.vibrate_seat) Vibration.vibrate(350);
  if (prefs.sound) {
    if (response.sound === 'high') sounds.play('warning');
    else if (response.sound === 'low') sounds.play('chime');
  }
  if (prefs.voice && RANK[trip.level] > RANK[lastLevel] && RANK[trip.level] >= RANK.warning && now - lastSpokenAt > 6000) {
    lastSpokenAt = now;
    Speech.speak(response.message, { rate: 1.05 });
  }
  lastLevel = trip.level;

  if (response.sound === 'high' && AppState.currentState !== 'active' && now - lastBackgroundWarningAt > 10_000) {
    lastBackgroundWarningAt = now;
    void notify.showWarning(response.message);
  }
}

function startEmergency(state: TripState) {
  const prefs = settingsStore.get();
  if (prefs.sound) sounds.loop('siren');
  if (prefs.vibration) Vibration.vibrate([0, 700, 300], true);
  Brightness.setBrightnessAsync(1).catch(() => {});
  if (prefs.voice) Speech.speak(isCollapse(state) ? strings.emergency.collapseVoice : strings.emergency.voice, { rate: 1 });
  if (AppState.currentState !== 'active') void notify.showEmergency(state);
}

function stopEmergency() {
  sounds.stop('siren');
  Vibration.cancel();
  Speech.stop().catch(() => {});
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
      if (!wantService) lastLevel = 'safe';
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
