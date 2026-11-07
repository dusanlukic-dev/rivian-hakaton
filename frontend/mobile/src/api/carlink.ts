import Constants from 'expo-constants';
import { PermissionsAndroid, Platform } from 'react-native';

import { CarLinkModule, type FoundCar } from '../../modules/car-link';
import type { LiveHandlers } from './live';
import type { LiveMessage } from './types';

/** docs/BLUETOOTH.md: the car's GATT service and its two characteristics. */
export const CAR_SERVICE = '5afe0000-7a1e-4c55-8d2b-9c1e0f3a6b01';
const CAR_RX = '5afe0001-7a1e-4c55-8d2b-9c1e0f3a6b01';
const CAR_TX = '5afe0002-7a1e-4c55-8d2b-9c1e0f3a6b01';

const APP_VERSION = Constants.expoConfig?.version ?? '0';
const SCAN_MS = 10_000;
/** Android allows 5 scan starts per 30 s per app; one every 7 s stays clear of it. */
const SCAN_SPACING_MS = 7_000;
/** The remembered car didn't show up this long after another car did: Windows has likely changed its address. */
const PREFERRED_GRACE_MS = 1_500;
const CONNECT_MS = 15_000;
const HELLO_MS = 4_000;
const RECHECK_MS = 3_000;
/**
 * The car pings every 2 s. Silence this long means the link is dead even if Android never said so: it doesn't
 * report a drop when Bluetooth is switched off and on, and Windows keeps the radio link up when the gateway restarts.
 */
const SILENCE_MS = 7_000;

/** Where the Bluetooth link stands (for the UI). */
export type CarLinkPhase =
  | 'unsupported' // no Bluetooth LE, or the installed build predates the car link
  | 'no-permission' // "Nearby devices" not allowed yet
  | 'off' // Bluetooth is off
  | 'searching' // scanning for the car's service
  | 'connecting' // found it: connecting, subscribing, saying hello
  | 'connected' // the car answered and its computer is up
  | 'car-offline'; // Bluetooth works, but the car computer doesn't answer the gateway

/** The car's `hello` (docs/BLUETOOTH.md § Poruke). */
export interface CarHello {
  protocol: number;
  car: string | null;
  coordinator: boolean;
  server_url: string | null;
}

export interface CarLinkInfo {
  phase: CarLinkPhase;
  hello: CarHello | null;
  deviceId: string | null;
  deviceName: string | null;
}

export interface CarLinkHandlers extends LiveHandlers {
  onInfo(info: CarLinkInfo): void;
  /** Connected to this car: remember it, so the next start goes straight to it. */
  onCar(deviceId: string, name: string | null): void;
}

export interface CarReply {
  status: number;
  body: unknown;
}

export interface CarLinkConnection {
  stop(): void;
  /** Re-check right away (app in the foreground, permission granted, Bluetooth turned on, "Search again"). */
  kick(): void;
  /** A [K] REST call over Bluetooth. Rejects when the link is down or the car doesn't answer in time. */
  request(method: 'GET' | 'POST', path: string, body: unknown, token: string | null, timeoutMs: number): Promise<CarReply>;
}

export class CarLinkError extends Error {}

let active: CarLinkConnection | null = null;

/** The running Bluetooth link, if Bluetooth is the chosen transport. */
export function currentCarLink(): CarLinkConnection | null {
  return active;
}

/** Asks Android for "Nearby devices" (Android 12+) or location (older). True when granted. */
export async function requestCarLinkPermission(): Promise<'granted' | 'denied' | 'blocked'> {
  if (Platform.OS !== 'android') return 'denied';
  const wanted =
    Platform.Version >= 31
      ? [PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN, PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT]
      : [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];
  const result = await PermissionsAndroid.requestMultiple(wanted);
  if (wanted.every((p) => result[p] === PermissionsAndroid.RESULTS.GRANTED)) return 'granted';
  return wanted.some((p) => result[p] === PermissionsAndroid.RESULTS.NEVER_ASK_AGAIN) ? 'blocked' : 'denied';
}

/**
 * Keeps a Bluetooth link to the car open forever (docs/BLUETOOTH.md), with the same handlers as the WebSocket
 * (`connectLive`): `open` = the car answered `hello` and its computer is up. Finds the car by its service UUID
 * (preferring the remembered one), connects, says hello, then passes live messages on and matches responses to
 * requests. On any loss it searches again.
 */
export function connectCarLink(preferredId: string | null, handlers: CarLinkHandlers): CarLinkConnection {
  const native = CarLinkModule;
  let stopped = false;
  let ready = false;
  let knownId = preferredId;
  let info: CarLinkInfo = { phase: 'searching', hello: null, deviceId: preferredId, deviceName: null };
  let wake: (() => void) | null = null;
  let endSession: (() => void) | null = null;
  let cancelScan: (() => void) | null = null;
  let helloWaiter: ((hello: CarHello | null) => void) | null = null;
  let lastScanAt = 0;
  let lastHeardAt = 0;
  const pending = new Map<string, { resolve: (reply: CarReply) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>();

  const setInfo = (patch: Partial<CarLinkInfo>) => {
    info = { ...info, ...patch };
    handlers.onInfo(info);
  };

  const failPending = (reason: string) => {
    for (const [id, p] of pending) {
      clearTimeout(p.timer);
      pending.delete(id);
      p.reject(new CarLinkError(reason));
    }
  };

  const applyHello = (hello: CarHello) => {
    setInfo({ hello, phase: hello.coordinator ? 'connected' : 'car-offline' });
    handlers.onStatus(hello.coordinator ? 'open' : 'closed');
  };

  const onMessage = (json: string) => {
    let message: { type?: string; data?: unknown; id?: unknown; status?: unknown; body?: unknown };
    try {
      message = JSON.parse(json) as typeof message;
    } catch {
      return;
    }
    lastHeardAt = Date.now();
    if (message.type === 'ping') return;
    if (message.type === 'hello') {
      const hello = message.data as CarHello;
      if (helloWaiter) {
        helloWaiter(hello);
        helloWaiter = null;
      } else {
        applyHello(hello); // the car computer went away or came back
      }
      return;
    }
    if (message.type === 'response') {
      const id = String(message.id);
      const p = pending.get(id);
      if (!p) return;
      clearTimeout(p.timer);
      pending.delete(id);
      p.resolve({ status: Number(message.status) || 0, body: message.body ?? null });
      return;
    }
    handlers.onMessage(message as LiveMessage);
  };

  const subscriptions = native
    ? [
        native.addListener('onMessage', ({ json }) => onMessage(json)),
        native.addListener('onState', (event) => {
          if (event.state === 'disconnected') endSession?.();
          if (event.state === 'adapter-on') wake?.(); // retry now, not on the next 3 s check
        }),
      ]
    : [];

  /** A wait that `kick()` and `stop()` cut short. */
  const pause = (ms: number) =>
    new Promise<void>((resolve) => {
      const finish = () => {
        clearTimeout(timer);
        if (wake === finish) wake = null;
        resolve();
      };
      const timer = setTimeout(finish, ms);
      wake = finish;
    });

  /** A wait nothing cuts short (scan spacing must hold, or Android stops delivering scan results). */
  const hold = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

  const scan = (preferred: string | null) =>
    new Promise<FoundCar | null>((resolve) => {
      if (!native) {
        resolve(null);
        return;
      }
      let first: FoundCar | null = null;
      let grace: ReturnType<typeof setTimeout> | undefined;
      const done = (car: FoundCar | null) => {
        clearTimeout(timer);
        clearTimeout(grace);
        devices.remove();
        states.remove();
        cancelScan = null;
        native.stopScan();
        resolve(car);
      };
      const devices = native.addListener('onDevice', (car) => {
        if (!preferred || car.id === preferred) {
          done(car);
        } else if (!first) {
          first = car;
          grace = setTimeout(() => done(first), PREFERRED_GRACE_MS);
        }
      });
      const states = native.addListener('onState', (event) => {
        if (event.state === 'scan-failed') done(null);
      });
      const timer = setTimeout(() => done(first), SCAN_MS);
      cancelScan = () => done(null);
      lastScanAt = Date.now();
      native.startScan(CAR_SERVICE);
    });

  /** Connects to `car` and waits for its hello. True = the session is up (it ends when `endSession` runs). */
  const open = async (car: { id: string; name: string | null }): Promise<boolean> => {
    if (!native) return false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([
        native.connect(car.id, CAR_SERVICE, CAR_RX, CAR_TX),
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(new CarLinkError('connect timed out')), CONNECT_MS);
        }),
      ]);
    } catch {
      native.disconnect();
      return false;
    } finally {
      clearTimeout(timer);
    }
    ready = true;
    const hello = await new Promise<CarHello | null>((resolve) => {
      const t = setTimeout(() => {
        helloWaiter = null;
        resolve(null);
      }, HELLO_MS);
      helloWaiter = (h) => {
        clearTimeout(t);
        resolve(h);
      };
      native.send(JSON.stringify({ type: 'hello', app: 'mobile', version: APP_VERSION })).catch(() => {});
    });
    if (!hello || stopped) {
      ready = false;
      native.disconnect();
      return false;
    }
    knownId = car.id;
    applyHello(hello);
    handlers.onCar(car.id, hello.car ?? car.name);
    return true;
  };

  const loop = async () => {
    let failures = 0;
    while (!stopped) {
      const availability = native ? native.status() : 'unsupported';
      if (availability !== 'ready') {
        setInfo({ phase: availability, hello: null });
        handlers.onStatus('closed');
        await pause(RECHECK_MS);
        continue;
      }

      // Always scan first. Windows advertises from a new random address now and then (A3:5D, EB:7A, 6E:9E within
      // minutes on the demo laptop), so connecting straight to the last address mostly ends in a 10 s timeout
      // (status 147). The last address is only preferred among what the scan finds.
      setInfo({ phase: 'searching', hello: null });
      handlers.onStatus('connecting');
      const wait = lastScanAt + SCAN_SPACING_MS - Date.now();
      if (wait > 0) await hold(wait);
      if (stopped) break;
      const car = await scan(knownId);
      if (stopped) break;
      if (!car) {
        failures += 1;
        handlers.onStatus('closed');
        await pause(Math.min(1000 * failures, 5000));
        continue;
      }

      setInfo({ phase: 'connecting', deviceId: car.id, deviceName: car.name ?? info.deviceName });
      handlers.onStatus('connecting');
      const ended = new Promise<void>((resolve) => {
        endSession = resolve;
      });
      const up = await open(car);
      if (up) {
        failures = 0;
        lastHeardAt = Date.now();
        const watchdog = setInterval(() => {
          if (Date.now() - lastHeardAt < SILENCE_MS) return;
          native?.disconnect(); // tears the GATT client down; its 'disconnected' event ends the session
          endSession?.();
        }, 1000);
        await ended;
        clearInterval(watchdog);
      } else {
        failures += 1;
      }
      endSession = null;
      ready = false;
      helloWaiter = null;
      failPending('The Bluetooth link to the car dropped.');
      if (stopped) break;
      setInfo({ phase: 'searching', hello: null });
      handlers.onStatus('closed');
      await pause(up ? 500 : Math.min(1000 * failures, 5000));
    }
  };

  const connection: CarLinkConnection = {
    stop() {
      stopped = true;
      cancelScan?.();
      wake?.();
      endSession?.();
      failPending('The Bluetooth link was closed.');
      subscriptions.forEach((s) => s.remove());
      native?.disconnect();
      if (active === connection) active = null;
    },
    kick() {
      wake?.();
    },
    request(method, path, body, token, timeoutMs) {
      if (!native || !ready) return Promise.reject(new CarLinkError('Not connected to the car over Bluetooth.'));
      const id = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
      return new Promise<CarReply>((resolve, reject) => {
        const timer = setTimeout(() => {
          pending.delete(id);
          reject(new CarLinkError('The car did not answer in time.'));
        }, timeoutMs);
        pending.set(id, { resolve, reject, timer });
        native.send(JSON.stringify({ type: 'request', id, method, path, token, body: body ?? null })).catch(() => {
          clearTimeout(timer);
          pending.delete(id);
          reject(new CarLinkError('Could not send to the car over Bluetooth.'));
        });
      });
    },
  };

  active = connection;
  handlers.onInfo(info);
  handlers.onStatus('connecting');
  void loop();
  return connection;
}
