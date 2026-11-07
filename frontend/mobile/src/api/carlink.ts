import Constants from 'expo-constants';
import { AppState, PermissionsAndroid, Platform } from 'react-native';

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
/** The remembered car advertises no name: wait this long for its last address before trying another car. */
const PREFERRED_GRACE_MS = 1_500;
/** A car not heard this long leaves the list (it went away, or Windows moved it to a new address). */
const NEARBY_MS = 15_000;
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
  | 'choose' // connects to nothing by itself: lists the cars nearby until the driver picks one
  | 'searching' // looking for the remembered car
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

/** A car the scans hear, and when they last did. */
export interface NearbyCar extends FoundCar {
  seenAt: number;
}

/** The car the driver picked (kept in settings), and whether to connect to it by itself. */
export interface CarChoice {
  /** Its Bluetooth address at the last connection. Windows changes it now and then. */
  id: string | null;
  /** The name it advertises (on Windows the laptop's Bluetooth name). It stays when the address changes. */
  scanName: string | null;
  /** The name from its hello (the gateway's `--name`). */
  name: string | null;
  /** Reconnect by itself whenever it's in range: on once the driver connects, off after Disconnect. */
  auto: boolean;
}

export interface CarLinkHandlers extends LiveHandlers {
  onInfo(info: CarLinkInfo): void;
  /** Connected to this car: remember it and reconnect to it by itself from now on. */
  onCar(car: { id: string; scanName: string | null; name: string | null }): void;
  /** The cars nearby, strongest signal first, for the driver to pick from. */
  onNearby(cars: NearbyCar[]): void;
}

export interface CarReply {
  status: number;
  body: unknown;
}

export interface CarLinkConnection {
  stop(): void;
  /** Re-check right away (app in the foreground, permission granted, Bluetooth turned on, "Search again"). */
  kick(): void;
  /** Connect to this car from the list now: the driver tapped it. */
  choose(car: FoundCar): void;
  /** Drop the link. With `auto` off in the choice it then only lists the cars nearby. */
  release(): void;
  /** A [K] REST call over Bluetooth. Rejects when the link is down or the car doesn't answer in time. */
  request(method: 'GET' | 'POST', path: string, body: unknown, token: string | null, timeoutMs: number): Promise<CarReply>;
}

export class CarLinkError extends Error {}

/** A car to connect to. `verify`: it was only a guess, so its hello has to name the remembered car. */
type Pick = { car: FoundCar; verify: boolean };

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

const seeksCar = (choice: CarChoice) => choice.auto && (choice.id !== null || choice.scanName !== null);

/** The remembered car among what a scan hears: the same address, or (new address) the same advertised name. */
const isChosen = (car: FoundCar, choice: CarChoice) =>
  car.id === choice.id || (choice.scanName !== null && car.name === choice.scanName);

/**
 * Keeps the Bluetooth link to the car (docs/BLUETOOTH.md), with the same handlers as the WebSocket (`connectLive`):
 * `open` = the car answered `hello` and its computer is up. It connects only to a car the driver picked: until then
 * it lists the cars nearby (`onNearby`) and waits for `choose`. Once connected, that car is remembered and the link
 * finds it again by itself after every loss, until `release` with `auto` off (Disconnect).
 */
export function connectCarLink(getChoice: () => CarChoice, handlers: CarLinkHandlers): CarLinkConnection {
  const native = CarLinkModule;
  let stopped = false;
  let ready = false;
  const initial = getChoice();
  let info: CarLinkInfo = { phase: seeksCar(initial) ? 'searching' : 'choose', hello: null, deviceId: initial.id, deviceName: null };
  let wake: (() => void) | null = null;
  let endSession: (() => void) | null = null;
  let cancelScan: (() => void) | null = null;
  /** Ends the running scan with the driver's pick. */
  let pickNow: ((car: FoundCar) => void) | null = null;
  /** The car the driver tapped, until the loop takes it. */
  let target: FoundCar | null = null;
  let helloWaiter: ((hello: CarHello | null) => void) | null = null;
  let lastScanAt = 0;
  let lastHeardAt = 0;
  let listedAt = 0;
  const nearby = new Map<string, NearbyCar>();
  /** Answered with another car's name (only nameless cars get tried on a guess). */
  const rejected = new Set<string>();
  const pending = new Map<string, { resolve: (reply: CarReply) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>();

  const setInfo = (patch: Partial<CarLinkInfo>) => {
    info = { ...info, ...patch };
    handlers.onInfo(info);
  };

  /** Hands the list to the UI: at once for a new car, else at most once a second (scans report many times a second). */
  const publishNearby = (now: boolean) => {
    const at = Date.now();
    if (!now && at - listedAt < 1000) return;
    listedAt = at;
    for (const [id, car] of nearby) if (at - car.seenAt > NEARBY_MS) nearby.delete(id);
    handlers.onNearby([...nearby.values()].sort((a, b) => b.rssi - a.rssi));
  };

  const clearNearby = () => {
    if (nearby.size === 0) return;
    nearby.clear();
    publishNearby(true);
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

  /**
   * One scan round. Lists every car it hears. Resolves with the car to connect to (the driver's pick, or with `auto`
   * the remembered car), or null when the round ends without one.
   */
  const scan = () =>
    new Promise<Pick | null>((resolve) => {
      if (!native) {
        resolve(null);
        return;
      }
      let guess: FoundCar | null = null;
      let grace: ReturnType<typeof setTimeout> | undefined;
      const done = (pick: Pick | null) => {
        clearTimeout(timer);
        clearTimeout(grace);
        devices.remove();
        states.remove();
        cancelScan = null;
        pickNow = null;
        native.stopScan();
        publishNearby(true);
        resolve(pick);
      };
      const devices = native.addListener('onDevice', (car) => {
        const isNew = !nearby.has(car.id);
        nearby.set(car.id, { ...car, seenAt: Date.now() });
        publishNearby(isNew);
        const choice = getChoice(); // fresh: Disconnect may have come in during the round
        if (!seeksCar(choice)) return; // only listing: the driver picks
        if (isChosen(car, choice)) {
          done({ car, verify: false });
        } else if (choice.scanName === null && !guess && !rejected.has(car.id)) {
          // The remembered car advertises no name, so a new address hides it: try this one, its hello tells.
          guess = car;
          grace = setTimeout(() => done(guess && { car: guess, verify: true }), PREFERRED_GRACE_MS);
        }
      });
      const states = native.addListener('onState', (event) => {
        if (event.state === 'scan-failed') done(null);
      });
      const timer = setTimeout(() => done(null), SCAN_MS);
      cancelScan = () => done(null);
      pickNow = (car) => done({ car, verify: false });
      lastScanAt = Date.now();
      native.startScan(CAR_SERVICE);
    });

  /** Connects to `car` and waits for its hello. True = the session is up (it ends when `endSession` runs). */
  const open = async ({ car, verify }: Pick): Promise<boolean> => {
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
    const remembered = getChoice().name;
    const otherCar = verify && hello !== null && hello.car !== null && remembered !== null && hello.car !== remembered;
    if (!hello || stopped || otherCar) {
      if (otherCar) rejected.add(car.id);
      ready = false;
      native.disconnect();
      return false;
    }
    clearNearby();
    applyHello(hello);
    handlers.onCar({ id: car.id, scanName: car.name, name: hello.car ?? car.name });
    return true;
  };

  const loop = async () => {
    let failures = 0;
    while (!stopped) {
      const availability = native ? native.status() : 'unsupported';
      if (availability !== 'ready') {
        clearNearby();
        setInfo({ phase: availability, hello: null });
        handlers.onStatus('closed');
        await pause(RECHECK_MS);
        continue;
      }

      const seeking = target !== null || seeksCar(getChoice());
      setInfo({ phase: seeking ? 'searching' : 'choose', hello: null });
      handlers.onStatus(seeking ? 'connecting' : 'closed');
      if (!seeking && AppState.currentState !== 'active') {
        await pause(RECHECK_MS); // only listing, and nobody looks: no scanning in the background
        continue;
      }

      // Scan first, unless the driver just tapped a car (its address is fresh from the list). Windows advertises from
      // a new random address now and then (A3:5D, EB:7A, 6E:9E within minutes on the demo laptop), so connecting
      // straight to the last saved address mostly ends in a 10 s timeout (status 147).
      let pick: Pick | null = null;
      if (!target) {
        const wait = lastScanAt + SCAN_SPACING_MS - Date.now();
        if (wait > 0) await hold(wait);
        if (stopped) break;
        if (!target) pick = await scan();
      }
      if (target) pick = { car: target, verify: false };
      target = null;
      if (stopped) break;
      if (!pick) {
        if (seeking) {
          failures += 1;
          handlers.onStatus('closed');
          await pause(Math.min(1000 * failures, 5000));
        }
        continue;
      }

      setInfo({ phase: 'connecting', deviceId: pick.car.id, deviceName: pick.car.name ?? info.deviceName });
      handlers.onStatus('connecting');
      const ended = new Promise<void>((resolve) => {
        endSession = resolve;
      });
      const up = await open(pick);
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
      setInfo({ phase: seeksCar(getChoice()) ? 'searching' : 'choose', hello: null });
      handlers.onStatus('closed');
      await pause(up ? 500 : Math.min(1000 * failures, 5000));
    }
  };

  const connection: CarLinkConnection = {
    stop() {
      stopped = true;
      target = null;
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
    choose(car) {
      if (stopped) return;
      target = car;
      if (ready) {
        native?.disconnect(); // another car: drop this one, the loop then takes the target
        endSession?.();
      } else if (pickNow) {
        pickNow(car);
      } else {
        wake?.();
      }
    },
    release() {
      target = null;
      native?.disconnect();
      endSession?.();
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
  handlers.onStatus(seeksCar(initial) ? 'connecting' : 'closed');
  void loop();
  return connection;
}
