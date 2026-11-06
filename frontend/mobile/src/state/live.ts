import { AppState } from 'react-native';

import { connectLive, type LiveConnection, type LiveStatus } from '@/api/live';
import type { LiveMessage, SafetyLevel, TripState, TripSummary } from '@/api/types';
import { createStore, useStore } from '@/lib/store';

import { settingsStore } from './settings';

export interface LiveState {
  status: LiveStatus | 'idle';
  /** Latest state of the active trip; null when no trip runs. */
  trip: TripState | null;
  /** +1 on every state-carrying message: the alert engine's "per message" rhythm (docs/API.md §7). */
  tick: number;
  lastMessageAt: number;
  /** Set by the `emergency` event; stays until the driver acknowledges. */
  emergency: TripState | null;
  /** Last finished trip (`trip_ended` or POST /end). */
  summary: TripSummary | null;
  /** True while a local test alert runs (Settings → Try the alerts). */
  simulated: boolean;
}

export const liveStore = createStore<LiveState>({
  status: 'idle',
  trip: null,
  tick: 0,
  lastMessageAt: 0,
  emergency: null,
  summary: null,
  simulated: false,
});

export function useLive<S>(select: (state: LiveState) => S): S {
  return useStore(liveStore, select);
}

function onMessage(message: LiveMessage) {
  const now = Date.now();
  switch (message.type) {
    case 'trip_started':
    case 'state': {
      const data = message.data;
      const started = message.type === 'trip_started';
      liveStore.set((s) => ({
        trip: data.status === 'active' ? data : null,
        tick: s.tick + 1,
        lastMessageAt: now,
        summary: started ? null : s.summary,
        simulated: false,
      }));
      break;
    }
    case 'emergency':
      // arrives right after the `state` of the same tick, so no extra tick here
      liveStore.set({ trip: message.data, emergency: message.data, lastMessageAt: now });
      break;
    case 'trip_ended': {
      const summary = message.data;
      liveStore.set((s) => ({
        trip: s.trip?.trip_id === summary.trip_id ? null : s.trip,
        emergency: null,
        summary,
        lastMessageAt: now,
      }));
      break;
    }
    default:
      break; // unknown event types are ignored on purpose
  }
}

let connection: LiveConnection | null = null;
let connectedAddress: string | null = null;
let started = false;

function connect(address: string) {
  connection?.stop();
  connectedAddress = address;
  connection = connectLive(address, { onMessage, onStatus: (status) => liveStore.set({ status }) });
}

/** Opens the socket to the configured address and follows address changes / app foregrounding. */
export function startLive() {
  if (started) return;
  started = true;
  connect(settingsStore.get().address);
  settingsStore.subscribe(() => {
    const { address } = settingsStore.get();
    if (address === connectedAddress) return;
    liveStore.set({ trip: null, emergency: null, status: 'connecting' });
    connect(address);
  });
  AppState.addEventListener('change', (state) => {
    if (state === 'active') connection?.kick();
  });
}

export const ackEmergency = () => liveStore.set({ emergency: null });

/** After POST /trips (the WebSocket confirms with `trip_started`). */
export const setActiveTrip = (trip: TripState) => liveStore.set({ trip, summary: null, lastMessageAt: Date.now() });

/** After POST /trips/{id}/end. */
export const setEndedTrip = (summary: TripSummary) => liveStore.set({ trip: null, emergency: null, summary });

function fakeState(level: SafetyLevel): TripState {
  const emergency = level === 'emergency';
  return {
    trip_id: 'test-alert',
    driver_id: 'test',
    status: 'active',
    score: emergency ? 6.4 : 41.8,
    level,
    active_behaviors: emergency ? { drowsy: 3 } : { looking_at_phone: 4 },
    response: {
      dashboard_light: emergency ? 'red' : 'yellow',
      vibrate_seat: true,
      sound: 'high',
      message: emergency
        ? 'Test emergency: this is what the driver gets.'
        : 'Test warning: this is what a distracted driver gets.',
    },
    emergency_alert_sent: emergency,
  };
}

let testTimer: ReturnType<typeof setInterval> | undefined;

/** Local preview of the alerts, no backend needed. Warning = 5 fake ticks; emergency stays until "I'm OK". */
export function runTestAlert(kind: 'warning' | 'emergency') {
  if (kind === 'emergency') {
    liveStore.set({ emergency: fakeState('emergency'), simulated: true });
    return;
  }
  clearInterval(testTimer);
  const real = liveStore.get().trip;
  let ticks = 0;
  liveStore.set((s) => ({ trip: fakeState('high_risk'), tick: s.tick + 1, lastMessageAt: Date.now(), simulated: true }));
  testTimer = setInterval(() => {
    ticks += 1;
    if (ticks >= 5) {
      clearInterval(testTimer);
      liveStore.set({ trip: real, simulated: false });
      return;
    }
    liveStore.set((s) => ({ tick: s.tick + 1, lastMessageAt: Date.now() }));
  }, 1000);
}
