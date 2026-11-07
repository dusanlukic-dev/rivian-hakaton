import { useEffect } from 'react';
import { Linking, StyleSheet, View } from 'react-native';
import Animated, {
  cancelAnimation,
  interpolateColor,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { isCollapse } from '@/config/behaviors';
import { strings } from '@/config/strings';
import { useNow } from '@/hooks/useNow';
import { formatScore } from '@/lib/format';
import { ackEmergency, isTestTrip, useLive, type ContactTextStatus } from '@/state/live';
import { useAuth } from '@/state/auth';
import { useSettings } from '@/state/settings';
import { colors } from '@/theme/colors';

import { Button, Icon, Txt, type IconName } from './ui';

// 250 ms up + 250 ms down = 2 Hz. Never faster than 3 Hz (photosensitivity, D14).
const HALF_PERIOD_MS = 250;
// `state` arrives ~2/s while driving. Older than this = the stream stalled (camera side stopped, socket
// dropped), so the last "loud alarm" state must not keep the screen flashing.
const STALE_MS = 3000;

/** Red full-screen pulse while the backend asks for the loud alarm (response.sound === "high"). */
function FlashOverlay() {
  const previewAlarm = useLive((s) => s.preview?.response.sound === 'high');
  const liveAlarm = useLive((s) => s.trip?.response.sound === 'high');
  const lastMessageAt = useLive((s) => s.lastMessageAt);
  const emergency = useLive((s) => s.emergency !== null);
  const enabled = useSettings((s) => s.flash);
  const now = useNow(1000);
  const active = !emergency && (previewAlarm || (liveAlarm && now - lastMessageAt < STALE_MS));
  const opacity = useSharedValue(0);

  useEffect(() => {
    if (active && enabled) {
      opacity.set(
        withRepeat(
          withSequence(withTiming(0.55, { duration: HALF_PERIOD_MS }), withTiming(0.08, { duration: HALF_PERIOD_MS })),
          -1,
        ),
      );
    } else {
      cancelAnimation(opacity);
      opacity.set(withTiming(0, { duration: 200 }));
    }
  }, [active, enabled, opacity]);

  const style = useAnimatedStyle(() => ({ opacity: opacity.get() }));
  return <Animated.View style={[StyleSheet.absoluteFill, styles.flash, style]} />;
}

/** Score < 10: full-screen red emergency mode until the driver taps "I'm OK". */
function EmergencyOverlay() {
  const emergency = useLive((s) => s.emergency);
  // The account's emergency contact (Profile tab, PATCH /auth/me).
  const contactName = useAuth((a) => a.user?.emergency_contact?.name ?? '');
  const contactPhone = useAuth((a) => a.user?.emergency_contact?.phone ?? '');
  const driver = useAuth((a) => a.user?.display_name ?? '');
  const contactText = useLive((s) => s.contactText);
  const insets = useSafeAreaInsets();
  const t = useSharedValue(0);

  const visible = emergency !== null;
  useEffect(() => {
    if (!visible) return;
    t.set(withRepeat(withTiming(1, { duration: HALF_PERIOD_MS }), -1, true));
    return () => cancelAnimation(t);
  }, [visible, t]);

  const pulse = useAnimatedStyle(() => ({
    backgroundColor: interpolateColor(t.get(), [0, 1], [colors.alarmDeep, colors.alarm]),
  }));

  if (!emergency) return null;
  const contact = contactName || strings.profile.contactFallback;
  const collapse = isCollapse(emergency);
  const smsBody = collapse ? strings.emergency.collapseSmsBody(driver) : strings.emergency.smsBody(driver);
  // The automatic text (alerts/sms.ts): a test never sends one, it only says what would happen.
  const textLine = !contactPhone
    ? null
    : isTestTrip(emergency.trip_id)
      ? { icon: 'message-text-outline' as const, text: strings.emergency.textTest(contact) }
      : contactText?.tripId === emergency.trip_id
        ? textStatusLine(contactText.status, contact)
        : null;

  return (
    <Animated.View style={[StyleSheet.absoluteFill, styles.emergency, pulse, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 }]}>
      <View style={styles.emergencyTop}>
        <Icon name="alert-octagon" size={96} color="#fff" />
        <Txt size="xxl" weight="900" style={styles.white}>
          {strings.emergency.title}
        </Txt>
        <Txt size="lg" weight="700" style={[styles.white, styles.center]}>
          {collapse ? strings.emergency.collapseSubtitle : strings.emergency.subtitle}
        </Txt>
        <Txt size="md" style={[styles.white, styles.center, styles.message]}>
          {emergency.response.message}
        </Txt>
        <Txt size="xl" weight="900" style={styles.white}>
          {formatScore(emergency.score)} / 100
        </Txt>
      </View>
      <View style={styles.actions}>
        <Button size="lg" label={strings.emergency.ack} icon="check-circle" onPress={ackEmergency} style={styles.ackButton} />
        {textLine ? (
          <View style={styles.textLine}>
            <Icon name={textLine.icon} size={20} color="#fff" />
            <Txt size="sm" weight="700" style={[styles.white, styles.flex]}>
              {textLine.text}
            </Txt>
          </View>
        ) : null}
        {contactPhone ? (
          <View style={styles.row}>
            <Button
              label={strings.emergency.text(contact)}
              icon="message-text"
              variant="secondary"
              style={styles.flex}
              onPress={() =>
                Linking.openURL(`sms:${contactPhone}?body=${encodeURIComponent(smsBody)}`).catch(
                  (e: unknown) => console.warn('[emergency] sms', e),
                )
              }
            />
            <Button
              label={strings.emergency.call(contact)}
              icon="phone"
              variant="secondary"
              style={styles.flex}
              onPress={() => Linking.openURL(`tel:${contactPhone}`).catch((e: unknown) => console.warn('[emergency] call', e))}
            />
          </View>
        ) : null}
      </View>
    </Animated.View>
  );
}

function textStatusLine(status: ContactTextStatus, name: string): { icon: IconName; text: string } {
  switch (status) {
    case 'sending':
      return { icon: 'message-processing-outline', text: strings.emergency.texting(name) };
    case 'sent':
      return { icon: 'message-check-outline', text: strings.emergency.texted(name) };
    case 'no_permission':
      return { icon: 'message-alert-outline', text: strings.emergency.textOff(name) };
    default:
      return { icon: 'message-alert-outline', text: strings.emergency.textFailed(name) };
  }
}

/** Mounted once in the root layout, above every screen. */
export function AlertOverlays() {
  return (
    <>
      <FlashOverlay />
      <EmergencyOverlay />
    </>
  );
}

const styles = StyleSheet.create({
  flash: { backgroundColor: colors.alarm, pointerEvents: 'none' },
  emergency: { paddingHorizontal: 24, justifyContent: 'space-between', zIndex: 100, elevation: 100 },
  emergencyTop: { alignItems: 'center', gap: 12, marginTop: 24 },
  white: { color: '#fff' },
  center: { textAlign: 'center' },
  message: { opacity: 0.95, maxWidth: 340 },
  actions: { gap: 12 },
  ackButton: { backgroundColor: '#fff', borderColor: '#fff' },
  row: { flexDirection: 'row', gap: 12 },
  flex: { flex: 1 },
  textLine: { flexDirection: 'row', alignItems: 'center', gap: 8, justifyContent: 'center' },
});
