import { AppState } from 'react-native';

import { connectCarLink, currentCarLink, type CarChoice, type CarLinkInfo, type NearbyCar } from '@/api/carlink';
import { ApiError, api } from '@/api/client';
import { connectLive, type LiveConnection, type LiveStatus } from '@/api/live';
import type { LiveMessage, SafetyLevel, TripSection, TripState, TripSummary } from '@/api/types';
import { createStore, useStore } from '@/lib/store';

import { settingsStore } from './settings';

/**
 * Whether the car computer answers. 'checking' until the first attempt on the current address resolves; it then
 * stays 'offline' while the socket retries, so screens don't flicker between "connecting" and "offline".
 */
export type LinkState = 'checking' | 'online' | 'offline';

export interface LiveState {
  status: LiveStatus | 'idle';
  link: LinkState;
  /** Latest state of the active trip; null when no trip runs. */
  trip: TripState | null;
  /** +1 on every state-carrying message: the alert engine's "per message" rhythm (docs/API.md §7). */
  tick: number;
  lastMessageAt: number;
  /** Set by the `emergency` event; stays until the driver acknowledges. */
  emergency: TripState | null;
  /** Last finished trip (`trip_ended` or POST /end). */
  summary: TripSummary | null;
  /**
   * Local test alert (Settings → Try the alerts). Shown and played instead of `trip` while set, but never
   * written into `trip`: a test can't leave a fake trip behind (that used to keep the red flash on forever).
   */
  preview: TripState | null;
  /** The active trip's latest section summaries (WS `section`, one per 2 s), oldest first: the last ~minute. */
  sections: TripSection[];
  /** The Bluetooth link's phase and the car's hello; null on the Wi-Fi link. */
  carLink: CarLinkInfo | null;
  /** Cars the Bluetooth scans hear, strongest first (Car connection → Cars nearby). */
  nearbyCars: NearbyCar[];
}

/** 30 sections × 2 s = the last minute on the Drive screen. */
const RECENT_SECTIONS = 30;

export const liveStore = createStore<LiveState>({
  status: 'idle',
  link: 'checking',
  trip: null,
  tick: 0,
  lastMessageAt: 0,
  emergency: null,
  summary: null,
  preview: null,
  sections: [],
  carLink: null,
  nearbyCars: [],
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
        sections: started ? [] : s.sections,
      }));
      break;
    }
    case 'section': {
      const section = message.data;
      liveStore.set((s) => {
        const sameTrip = s.sections.length === 0 || s.sections[s.sections.length - 1].trip_id === section.trip_id;
        const kept = sameTrip ? s.sections : [];
        return { sections: [...kept, section].slice(-RECENT_SECTIONS) };
      });
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
/** What the running connection is for: "bluetooth", or "wifi:<address>". A change means reconnect. */
let connectedTo: string | null = null;
let started = false;

const linkKey = () => {
  const { carLink, address } = settingsStore.get();
  return carLink === 'wifi' ? `wifi:${address}` : 'bluetooth';
};

function onStatus(status: LiveStatus) {
  if (status === 'open') liveStore.set({ status, link: 'online' });
  else if (status === 'closed') liveStore.set({ status, link: 'offline' });
  else liveStore.set({ status });
  if (status === 'open') void checkTripStillRuns();
}

/** Opens the chosen car link: Bluetooth (docs/BLUETOOTH.md) or the WebSocket on the Wi-Fi/USB address. */
function connect() {
  connection?.stop();
  connectedTo = linkKey();
  const { carLink, address } = settingsStore.get();
  liveStore.set({ link: 'checking', carLink: null, nearbyCars: [] });
  if (carLink === 'wifi') {
    connection = connectLive(address, { onMessage, onStatus });
    return;
  }
  connection = connectCarLink(carChoice, {
    onMessage,
    onStatus,
    onInfo: (carLink) => liveStore.set({ carLink }),
    onNearby: (nearbyCars) => liveStore.set({ nearbyCars }),
    onCar: ({ id, scanName, name }) => {
      const s = settingsStore.get();
      if (s.carDeviceId !== id || s.carScanName !== scanName || s.carName !== name || !s.carAuto) {
        settingsStore.set({ carDeviceId: id, carScanName: scanName, carName: name, carAuto: true });
      }
    },
  });
}

/** The picked car, read fresh by the Bluetooth link on every decision. */
function carChoice(): CarChoice {
  const s = settingsStore.get();
  return { id: s.carDeviceId, scanName: s.carScanName, name: s.carName, auto: s.carAuto };
}

/** Re-checks the car link right away (after granting Bluetooth, turning it on, or "Search again"). */
export const retryCarLink = () => connection?.kick();

/** The driver tapped a car in Cars nearby: connect to it now. Once connected it's the remembered car. */
export const connectToCar = (car: NearbyCar) => currentCarLink()?.choose(car);

/** Connect to the remembered car again (after Disconnect); from then on it reconnects by itself. */
export function reconnectCar() {
  settingsStore.set({ carAuto: true });
  retryCarLink();
}

/** Disconnects, and stays disconnected until the driver connects again. */
export function disconnectCar() {
  settingsStore.set({ carAuto: false });
  currentCarLink()?.release();
}

/** Forgets the remembered car; the phone then only lists the cars nearby until the driver picks one. */
export function forgetCar() {
  settingsStore.set({ carDeviceId: null, carName: null, carScanName: null, carAuto: false });
  currentCarLink()?.release();
}

/** Resolves once the first connection attempt on the current address has an answer, or after `timeoutMs`. */
export function waitForLink(timeoutMs: number): Promise<void> {
  return new Promise((resolve) => {
    let unsubscribe = () => {};
    const finish = () => {
      clearTimeout(timer);
      unsubscribe();
      resolve();
    };
    const timer = setTimeout(finish, timeoutMs);
    unsubscribe = liveStore.subscribe(() => {
      if (liveStore.get().link !== 'checking') finish();
    });
    if (liveStore.get().link !== 'checking') finish();
  });
}

/**
 * After a (re)connect the car only sends `state` if a trip runs. If ours is gone (the backend restarted: the
 * server closed it at its last section) nothing would ever say so, and the Drive screen would show it forever.
 */
async function checkTripStillRuns() {
  const trip = liveStore.get().trip;
  if (!trip || trip.trip_id === TEST_TRIP_ID) return;
  try {
    const state = await api.getTrip(trip.trip_id);
    if (state.status !== 'active') dropTrip(trip.trip_id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) dropTrip(trip.trip_id);
  }
}

/** The active trip ended without a `trip_ended` (backend restart): forget it, keep its id for the summary. */
export function dropTrip(tripId: string) {
  liveStore.set((s) => (s.trip?.trip_id === tripId ? { trip: null, emergency: null, sections: [] } : {}));
}

/** Opens the chosen car link and follows link / address changes and app foregrounding. */
export function startLive() {
  if (started) return;
  started = true;
  connect();
  settingsStore.subscribe(() => {
    if (linkKey() === connectedTo) return;
    liveStore.set({ trip: null, emergency: null, status: 'connecting' });
    connect();
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

const TEST_TRIP_ID = 'test-alert';

function fakeState(level: SafetyLevel): TripState {
  const emergency = level === 'emergency';
  return {
    trip_id: TEST_TRIP_ID,
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
    camera: null,
    speed_kmh: 80,
    speed_source: 'mock',
    emergency_alert_sent: emergency,
  };
}

const PREVIEW_TICKS = 5;
let previewTimer: ReturnType<typeof setInterval> | undefined;

/** Ends a running test alert right away (the warning preview, or a test emergency screen). */
export function stopTestAlert() {
  clearInterval(previewTimer);
  previewTimer = undefined;
  liveStore.set((s) => ({
    preview: null,
    emergency: s.emergency?.trip_id === TEST_TRIP_ID ? null : s.emergency,
  }));
}

/**
 * Local preview of the alerts, no backend needed. Warning = 5 fake ticks, one per second (pressing it again
 * restarts the 5 s); emergency stays until "I'm OK". The real trip is never touched.
 */
export function runTestAlert(kind: 'warning' | 'emergency') {
  if (kind === 'emergency') {
    liveStore.set({ emergency: fakeState('emergency') });
    return;
  }
  clearInterval(previewTimer);
  let ticks = 0;
  liveStore.set((s) => ({ preview: fakeState('high_risk'), tick: s.tick + 1 }));
  previewTimer = setInterval(() => {
    ticks += 1;
    if (ticks >= PREVIEW_TICKS) stopTestAlert();
    else liveStore.set((s) => ({ tick: s.tick + 1 }));
  }, 1000);
}
