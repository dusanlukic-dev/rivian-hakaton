import Constants from 'expo-constants';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import {
  ensureNotificationPermission,
  getPermissionState,
  openBatterySettings,
  openDndSettings,
  openFullScreenSettings,
  type PermissionState,
} from '@/alerts/notifications';
import { normalizeAddress } from '@/api/address';
import { api } from '@/api/client';
import { StatusPill } from '@/components/dashboard';
import { Button, Card, Icon, Screen, ScreenHeader, SectionLabel, TextField, ToggleRow, Txt, type IconName } from '@/components/ui';
import { strings } from '@/config/strings';
import { errorText } from '@/lib/format';
import { runTestAlert } from '@/state/live';
import { DEFAULT_ADDRESS, settingsStore, useSettings, type Settings } from '@/state/settings';
import { colors } from '@/theme/colors';

export default function SettingsScreen() {
  const ready = useSettings((s) => s.ready);
  const address = useSettings((s) => s.address);
  return (
    <Screen>
      <ScreenHeader title={strings.settings.title} right={<StatusPill />} />
      {/* keyed by the saved address so a QR scan / USB preset refreshes the draft */}
      {ready ? <ConnectionCard key={address} saved={address} /> : null}
      <AlertToggles />
      <SectionLabel>{strings.settings.tryAlerts}</SectionLabel>
      <Card>
        <Txt size="sm" tone="muted">
          {strings.settings.tryHint}
        </Txt>
        <View style={styles.row}>
          <Button label={strings.settings.testWarning} icon="alarm-light" variant="secondary" style={styles.flex} onPress={() => runTestAlert('warning')} />
          <Button label={strings.settings.testEmergency} icon="alert-octagon" variant="danger" style={styles.flex} onPress={() => runTestAlert('emergency')} />
        </View>
      </Card>
      <Permissions />
      <SectionLabel>{strings.settings.about}</SectionLabel>
      <Card>
        <Txt weight="700">{strings.appName}</Txt>
        <Txt size="sm" tone="muted">
          {strings.tagline}
        </Txt>
        <Txt size="xs" tone="subtle">
          {strings.settings.version} {Constants.expoConfig?.version ?? '?'}
        </Txt>
      </Card>
    </Screen>
  );
}

function ConnectionCard({ saved }: { saved: string }) {
  const [draft, setDraft] = useState(saved);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [testing, setTesting] = useState(false);

  function save(value = draft) {
    const address = normalizeAddress(value);
    if (!address) {
      setResult({ ok: false, text: strings.settings.invalid });
      return null;
    }
    settingsStore.set({ address });
    return address;
  }

  async function test() {
    const address = normalizeAddress(draft);
    if (!address) {
      setResult({ ok: false, text: strings.settings.invalid });
      return;
    }
    setTesting(true);
    const started = Date.now();
    try {
      await api.health(address);
      setResult({ ok: true, text: strings.settings.testOk(Date.now() - started) });
    } catch (e) {
      setResult({ ok: false, text: errorText(e) });
    } finally {
      setTesting(false);
    }
  }

  return (
    <>
      <SectionLabel>{strings.settings.connection}</SectionLabel>
      <Card>
        <TextField
          label={strings.settings.address}
          hint={strings.settings.addressHint}
          value={draft}
          onChangeText={(text) => {
            setDraft(text);
            setResult(null);
          }}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="10.190.62.27:8000"
          onSubmitEditing={() => save()}
        />
        {result ? (
          <View style={styles.row}>
            <Icon name={result.ok ? 'check-circle' : 'alert-circle-outline'} size={18} color={result.ok ? colors.ok : colors.destructive} />
            <Txt size="sm" style={[styles.flex, { color: result.ok ? colors.ok : colors.destructive }]}>
              {result.text}
            </Txt>
          </View>
        ) : null}
        <View style={styles.row}>
          <Button label={strings.settings.save} icon="content-save" disabled={draft.trim() === saved} onPress={() => save()} style={styles.flex} />
          <Button label={strings.settings.test} icon="lan-connect" variant="secondary" loading={testing} onPress={() => void test()} style={styles.flex} />
        </View>
        <View style={styles.row}>
          <Button label={strings.settings.usb} icon="usb" variant="ghost" onPress={() => save(DEFAULT_ADDRESS)} style={styles.flex} />
          <Button label={strings.settings.scan} icon="qrcode-scan" variant="ghost" onPress={() => router.push('/scan')} style={styles.flex} />
        </View>
      </Card>
    </>
  );
}

const TOGGLES: { key: keyof Omit<Settings, 'address'>; icon: IconName; label: string }[] = [
  { key: 'sound', icon: 'volume-high', label: strings.settings.sound },
  { key: 'vibration', icon: 'vibrate', label: strings.settings.vibration },
  { key: 'flash', icon: 'alarm-light', label: strings.settings.flash },
  { key: 'voice', icon: 'account-voice', label: strings.settings.voice },
  { key: 'keepAwake', icon: 'cellphone-screenshot', label: strings.settings.keepAwake },
];

function AlertToggles() {
  const values = useSettings((s) => s);
  return (
    <>
      <SectionLabel>{strings.settings.alerts}</SectionLabel>
      <Card style={styles.tightCard}>
        {TOGGLES.map((t) => (
          <ToggleRow key={t.key} icon={t.icon} label={t.label} value={values[t.key]} onValueChange={(v) => settingsStore.set({ [t.key]: v })} />
        ))}
      </Card>
    </>
  );
}

function Permissions() {
  const [state, setState] = useState<PermissionState | null>(null);
  const refresh = useCallback(() => {
    getPermissionState()
      .then(setState)
      .catch(() => setState(null));
  }, []);
  useFocusEffect(refresh);

  const rows: { icon: IconName; label: string; ok: boolean | null; action: () => unknown }[] = [
    {
      icon: 'bell-ring',
      label: strings.settings.notifications,
      ok: state?.notifications ?? null,
      action: () => void ensureNotificationPermission().then(refresh),
    },
    { icon: 'cellphone-lock', label: strings.settings.fullScreen, ok: state?.fullScreen ?? null, action: openFullScreenSettings },
    { icon: 'battery-heart-variant', label: strings.settings.battery, ok: state?.batteryUnrestricted ?? null, action: openBatterySettings },
    { icon: 'minus-circle-off-outline', label: strings.settings.dnd, ok: null, action: openDndSettings },
  ];

  return (
    <>
      <SectionLabel>{strings.settings.permissions}</SectionLabel>
      <Card style={styles.tightCard}>
        <Txt size="sm" tone="muted">
          {strings.settings.permissionsHint}
        </Txt>
        {rows.map((r) => (
          <View key={r.label} style={styles.permRow}>
            <Icon name={r.icon} size={20} color={colors.muted} />
            <Txt style={styles.flex}>{r.label}</Txt>
            {r.ok ? (
              <Icon name="check-circle" size={22} color={colors.ok} />
            ) : (
              <Button label={r.ok === false ? strings.settings.allow : strings.settings.open} variant="secondary" onPress={() => void r.action()} />
            )}
          </View>
        ))}
      </Card>
    </>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  permRow: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 52 },
  tightCard: { gap: 4 },
});
