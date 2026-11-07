import { NativeModule, requireOptionalNativeModule } from 'expo';

/** What the phone can do right now. */
export type CarLinkAvailability = 'unsupported' | 'no-permission' | 'off' | 'ready';

export interface FoundCar {
  /** Bluetooth address, used to connect. */
  id: string;
  name: string | null;
  rssi: number;
}

export interface CarLinkStateEvent {
  /** adapter-off / adapter-on: the user switched Bluetooth (the connection is already torn down on off). */
  state: 'connecting' | 'ready' | 'disconnected' | 'scan-failed' | 'adapter-off' | 'adapter-on';
  reason: string | null;
  mtu: number;
}

type CarLinkEvents = {
  onDevice(event: FoundCar): void;
  onState(event: CarLinkStateEvent): void;
  onMessage(event: { json: string }): void;
};

declare class CarLinkNative extends NativeModule<CarLinkEvents> {
  status(): CarLinkAvailability;
  startScan(serviceUuid: string): void;
  stopScan(): void;
  connect(deviceId: string, serviceUuid: string, rxUuid: string, txUuid: string): Promise<{ mtu: number; maxFrame: number }>;
  disconnect(): void;
  /** Sends one JSON message (the module frames it). Resolves once the last frame is written. */
  send(json: string): Promise<void>;
}

/**
 * The car link's native side (docs/BLUETOOTH.md): a message pipe over Bluetooth LE. null when the installed dev
 * build predates the module (then the app falls back to "Bluetooth unsupported" instead of crashing).
 */
export const CarLinkModule = requireOptionalNativeModule<CarLinkNative>('CarLink');
