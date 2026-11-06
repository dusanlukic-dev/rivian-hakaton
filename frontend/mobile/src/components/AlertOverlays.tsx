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

import { strings } from '@/config/strings';
import { formatScore } from '@/lib/format';
import { ackEmergency, useLive } from '@/state/live';
import { useProfile } from '@/state/profile';
import { useSettings } from '@/state/settings';
import { colors } from '@/theme/colors';

import { Button, Icon, Txt } from './ui';

// 250 ms up + 250 ms down = 2 Hz. Never faster than 3 Hz (photosensitivity, D14).
const HALF_PERIOD_MS = 250;

/** Red full-screen pulse while the backend asks for the loud alarm (response.sound === "high"). */
function FlashOverlay() {
  const active = useLive((s) => s.trip?.response.sound === 'high' && s.emergency === null);
  const enabled = useSettings((s) => s.flash);
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
  const contactName = useProfile((p) => p.contactName);
  const contactPhone = useProfile((p) => p.contactPhone);
  const driver = useProfile((p) => p.name || p.driverId);
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

  return (
    <Animated.View style={[StyleSheet.absoluteFill, styles.emergency, pulse, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 }]}>
      <View style={styles.emergencyTop}>
        <Icon name="alert-octagon" size={96} color="#fff" />
        <Txt size="xxl" weight="900" style={styles.white}>
          {strings.emergency.title}
        </Txt>
        <Txt size="lg" weight="700" style={[styles.white, styles.center]}>
          {strings.emergency.subtitle}
        </Txt>
        <Txt size="md" style={[styles.white, styles.center, styles.message]}>
          {emergency.response.message}
        </Txt>
        <Txt size="xl" weight="900" style={styles.white}>
          {formatScore(emergency.score)} / 100
        </Txt>
      </View>
      <View style={styles.actions}>
        <Button big label={strings.emergency.ack} icon="check-circle" onPress={ackEmergency} style={styles.ackButton} />
        {contactPhone ? (
          <View style={styles.row}>
            <Button
              label={strings.emergency.text(contact)}
              icon="message-text"
              variant="secondary"
              style={styles.flex}
              onPress={() =>
                void Linking.openURL(`sms:${contactPhone}?body=${encodeURIComponent(strings.emergency.smsBody(driver))}`)
              }
            />
            <Button
              label={strings.emergency.call(contact)}
              icon="phone"
              variant="secondary"
              style={styles.flex}
              onPress={() => void Linking.openURL(`tel:${contactPhone}`)}
            />
          </View>
        ) : null}
      </View>
    </Animated.View>
  );
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
});
