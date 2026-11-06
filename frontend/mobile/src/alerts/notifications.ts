import Constants from 'expo-constants';
import * as IntentLauncher from 'expo-intent-launcher';
import {
  AndroidAudioContentType,
  AndroidAudioUsage,
  AndroidImportance as ChannelImportance,
  AndroidNotificationVisibility,
  setNotificationChannelAsync,
} from 'expo-notifications';
import { Platform } from 'react-native';
import notifee, {
  AndroidCategory,
  AndroidForegroundServiceType,
  AndroidImportance,
  AndroidNotificationSetting,
  AuthorizationStatus,
  EventType,
} from 'react-native-notify-kit';

import type { TripState } from '@/api/types';
import { strings } from '@/config/strings';
import { colors } from '@/theme/colors';

// Channels are immutable once created on a device: bump the suffix to change sound/importance.
const CHANNEL_ALARM = 'alarm_v1';
const CHANNEL_DRIVE = 'drive_v1';
const ID_DRIVE = 'drive';
const ID_EMERGENCY = 'emergency';
const ID_WARNING = 'warning';
const SMALL_ICON = 'ic_stat_alert';
const PACKAGE = Constants.expoConfig?.android?.package ?? 'dev.hakaton.driveralert';

const android = Platform.OS === 'android';

/**
 * Alarm channel is created through expo-notifications because only it can set AudioAttributes usage = ALARM
 * (plays on silent/vibrate, uses alarm volume). Notifications are then posted with notify-kit on that channel.
 */
export async function setupNotifications() {
  if (!android) return;
  await setNotificationChannelAsync(CHANNEL_ALARM, {
    name: 'Driving alerts',
    description: 'Loud alarm when you are distracted while driving',
    importance: ChannelImportance.MAX,
    sound: 'alarm_critical.wav',
    audioAttributes: {
      usage: AndroidAudioUsage.ALARM,
      contentType: AndroidAudioContentType.SONIFICATION,
    },
    vibrationPattern: [0, 700, 300, 700],
    enableVibrate: true,
    bypassDnd: true,
    lockscreenVisibility: AndroidNotificationVisibility.PUBLIC,
  });
  await setNotificationChannelAsync(CHANNEL_DRIVE, {
    name: 'Drive mode',
    description: 'Shown while a trip is being monitored',
    importance: ChannelImportance.LOW,
    sound: null,
    enableVibrate: false,
    showBadge: false,
  });
}

export async function ensureNotificationPermission(): Promise<boolean> {
  if (!android) return true;
  try {
    const current = await notifee.getNotificationSettings();
    if (current.authorizationStatus === AuthorizationStatus.AUTHORIZED) return true;
    const next = await notifee.requestPermission();
    return next.authorizationStatus === AuthorizationStatus.AUTHORIZED;
  } catch {
    return false;
  }
}

/** Foreground service = keeps the process + WebSocket alive while the phone is locked or in a pocket. */
export async function startDriveService() {
  if (!android) return;
  try {
    await notifee.displayNotification({
      id: ID_DRIVE,
      title: `${strings.appName} · Drive mode`,
      body: strings.notifications.driveBody,
      android: {
        channelId: CHANNEL_DRIVE,
        asForegroundService: true,
        foregroundServiceTypes: [AndroidForegroundServiceType.FOREGROUND_SERVICE_TYPE_SPECIAL_USE],
        ongoing: true,
        smallIcon: SMALL_ICON,
        color: colors.ok,
        pressAction: { id: 'default' },
      },
    });
  } catch (e) {
    console.warn('[notify] drive service failed', e);
  }
}

export async function stopDriveService() {
  if (!android) return;
  try {
    await notifee.stopForegroundService();
    await notifee.cancelNotification(ID_DRIVE);
  } catch {
    // already stopped
  }
}

/** Insistent alarm + full-screen intent: wakes a locked phone and shows the app over the lock screen. */
export async function showEmergency(state: TripState) {
  if (!android) return;
  try {
    await notifee.displayNotification({
      id: ID_EMERGENCY,
      title: strings.notifications.emergencyTitle,
      body: state.response.message,
      android: {
        channelId: CHANNEL_ALARM,
        category: AndroidCategory.ALARM,
        importance: AndroidImportance.HIGH,
        smallIcon: SMALL_ICON,
        color: colors.alarm,
        ongoing: true,
        loopSound: true,
        fullScreenAction: { id: 'default' },
        pressAction: { id: 'default' },
        actions: [{ title: strings.emergency.ack, pressAction: { id: 'ack' } }],
      },
    });
  } catch (e) {
    console.warn('[notify] emergency failed', e);
  }
}

/** Heads-up alarm for loud warnings while the app is in the background. */
export async function showWarning(message: string) {
  if (!android) return;
  try {
    await notifee.displayNotification({
      id: ID_WARNING,
      title: strings.notifications.warningTitle,
      body: message,
      android: {
        channelId: CHANNEL_ALARM,
        category: AndroidCategory.ALARM,
        importance: AndroidImportance.HIGH,
        smallIcon: SMALL_ICON,
        color: colors.alarm,
        timeoutAfter: 8000,
        pressAction: { id: 'default' },
      },
    });
  } catch (e) {
    console.warn('[notify] warning failed', e);
  }
}

export const cancelEmergency = () => notifee.cancelNotification(ID_EMERGENCY).catch(() => {});

/** Foreground taps on notification actions (background ones are handled in index.js). */
export function onNotificationAction(handler: (actionId: string) => void) {
  return notifee.onForegroundEvent(({ type, detail }) => {
    if (type === EventType.ACTION_PRESS && detail.pressAction?.id) handler(detail.pressAction.id);
  });
}

export interface PermissionState {
  notifications: boolean;
  fullScreen: boolean;
  batteryUnrestricted: boolean;
}

export async function getPermissionState(): Promise<PermissionState> {
  const settings = await notifee.getNotificationSettings();
  const batteryOptimized = await notifee.isBatteryOptimizationEnabled().catch(() => true);
  return {
    notifications: settings.authorizationStatus === AuthorizationStatus.AUTHORIZED,
    fullScreen: settings.android.fullScreenIntent === AndroidNotificationSetting.ENABLED,
    batteryUnrestricted: !batteryOptimized,
  };
}

// Every "Open" goes to THIS app's own page (verified on the A54, One UI 8 / Android 16). The generic
// pages (all apps' battery list, all apps' DND list) were what notify-kit's helpers and the first version
// opened; that was our code, not the dev build. The fallback is always this app's "App info" page.
const APP = `package:${PACKAGE}`;

/** This app's system "App info" page: every setting is one tap from there. */
export const openAppSettings = () =>
  IntentLauncher.startActivityAsync(IntentLauncher.ActivityAction.APPLICATION_DETAILS_SETTINGS, { data: APP }).catch(
    (e: unknown) => console.warn('[settings] app info', e),
  );

async function openOrFallBack(action: string, data?: string, fallback: () => Promise<unknown> = openAppSettings) {
  try {
    await IntentLauncher.startActivityAsync(action, data ? { data } : undefined);
  } catch {
    await fallback();
  }
}

/** Ask for the notification permission; if Android won't show the prompt anymore, open the app's notification page. */
export async function allowNotifications() {
  if (await ensureNotificationPermission()) return;
  await notifee.openNotificationSettings().catch(() => openAppSettings());
}

/** Android 14+: per-app "Full screen alerts" switch. */
export const openFullScreenSettings = () =>
  openOrFallBack('android.settings.MANAGE_APP_USE_FULL_SCREEN_INTENT', APP, () =>
    notifee.openNotificationSettings().catch(() => openAppSettings()),
  );

/**
 * System dialog "Let the app always run in the background?" for this app only (the manifest declares
 * REQUEST_IGNORE_BATTERY_OPTIMIZATIONS). If the app is already unrestricted, the dialog closes by itself.
 */
export const openBatterySettings = () => openOrFallBack('android.settings.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS', APP);

/** This app's "Do not disturb permission" switch, else the list of all apps with DND access. */
export const openDndSettings = () =>
  openOrFallBack('android.settings.NOTIFICATION_POLICY_ACCESS_DETAIL_SETTINGS', APP, () =>
    openOrFallBack('android.settings.NOTIFICATION_POLICY_ACCESS_SETTINGS'),
  );
