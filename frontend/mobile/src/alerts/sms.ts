import { Linking, PermissionsAndroid, Platform } from 'react-native';

import type { TripState } from '@/api/types';
import { isCollapse } from '@/config/behaviors';
import { strings } from '@/config/strings';
import { authStore } from '@/state/auth';
import { isTestTrip, setContactText } from '@/state/live';

import { sendSms } from '../../modules/system-access';

/**
 * The phone texts the account's emergency contact by itself when the car raises the `emergency` event (D54): the
 * phone has the SIM and works without the internet, and the driver may not be able to tap anything. The backend
 * decides when (score < 10 = confirmed collapse); this only delivers. The Text / Call buttons stay as a fallback.
 */
const android = Platform.OS === 'android';
// Read inside the functions only: the release build also evaluates the routes for the web/server manifest, where
// PermissionsAndroid is undefined, so touching it at import time breaks `createBundleReleaseJsAndAssets`.
const sendSmsPermission = () => PermissionsAndroid.PERMISSIONS.SEND_SMS;

/** Whether Android lets the app send texts. */
export async function smsAllowed(): Promise<boolean> {
  if (!android) return false;
  return PermissionsAndroid.check(sendSmsPermission()).catch(() => false);
}

/** Asks for SEND_SMS. If Android won't show the prompt anymore, opens the app's own settings page. */
export async function allowSms(): Promise<boolean> {
  if (!android) return false;
  const result = await PermissionsAndroid.request(sendSmsPermission());
  if (result === PermissionsAndroid.RESULTS.GRANTED) return true;
  if (result === PermissionsAndroid.RESULTS.NEVER_ASK_AGAIN) await Linking.openSettings().catch(() => {});
  return false;
}

/**
 * Before a trip: with a contact saved, ask for SEND_SMS now, while the driver can still answer. During the emergency
 * nothing is ever asked: the text just goes out (or the screen says texts are off). Once the driver picked
 * "Don't ask again", Android answers at once without a dialog, so this never nags.
 */
export async function ensureSmsPermission(): Promise<void> {
  if (!android || !contactNumber() || (await smsAllowed())) return;
  await PermissionsAndroid.request(sendSmsPermission()).catch(() => {});
}

/** The account's contact as the phone dials it: digits and a leading +, no spaces or dashes. */
export function contactNumber(): string | null {
  const phone = authStore.get().user?.emergency_contact?.phone?.replace(/[^\d+]/g, '');
  return phone || null;
}

/** The text for this emergency, signed with the driver's name. */
export function emergencyText(state: TripState): string {
  const driver = authStore.get().user?.display_name ?? '';
  return isCollapse(state) ? strings.emergency.collapseSmsBody(driver) : strings.emergency.smsBody(driver);
}

const texted = new Set<string>();

/** Texts the contact once per trip. Test emergencies never text anyone. */
export async function textEmergencyContact(state: TripState) {
  const phone = contactNumber();
  if (!android || !phone || isTestTrip(state.trip_id) || texted.has(state.trip_id)) return;
  texted.add(state.trip_id);
  setContactText(state.trip_id, 'sending');
  const result = await sendSms(phone, emergencyText(state));
  setContactText(state.trip_id, result);
  if (result !== 'sent') console.warn('[sms] emergency text', result);
}
