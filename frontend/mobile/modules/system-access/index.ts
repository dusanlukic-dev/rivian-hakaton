import { requireOptionalNativeModule } from 'expo';

/** What happened to a text: the network took it, it failed, no answer in 30 s, SEND_SMS missing, or no way to send. */
export type SmsResult = 'sent' | 'failed' | 'timeout' | 'no_permission' | 'unavailable';

interface SystemAccessModule {
  isDndAccessGranted(): boolean;
  /** Added after the first builds of this module: missing in an older dev build. */
  sendSms?(phone: string, body: string): Promise<SmsResult>;
}

// Optional: a dev build made before this module existed simply reports "unknown" instead of crashing.
const native = requireOptionalNativeModule<SystemAccessModule>('SystemAccess');

/** Whether this app may override Do Not Disturb. null = unknown (not Android, or the build lacks the module). */
export function isDndAccessGranted(): boolean | null {
  try {
    return native ? native.isDndAccessGranted() : null;
  } catch {
    return null;
  }
}

/** Sends a text straight from the phone (SmsManager), without opening the SMS app. Needs SEND_SMS. */
export async function sendSms(phone: string, body: string): Promise<SmsResult> {
  if (!native?.sendSms) return 'unavailable';
  try {
    return await native.sendSms(phone, body);
  } catch {
    return 'failed';
  }
}
