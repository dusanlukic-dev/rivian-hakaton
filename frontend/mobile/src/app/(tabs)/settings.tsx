import Constants from 'expo-constants';
import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, View } from 'react-native';

import {
  allowNotifications,
  openAppSettings,
  openBatterySettings,
  openDndSettings,
  openFullScreenSettings,
} from '@/alerts/notifications';
import { ConnectionCard } from '@/components/connection';
import { StatusPill } from '@/components/dashboard';
import { Button, Card, Icon, Screen, ScreenHeader, SectionLabel, ToggleRow, Txt, type IconName } from '@/components/ui';
import { strings } from '@/config/strings';
import { runTestAlert, stopTestAlert, useLive } from '@/state/live';
import { refreshPermissions, usePermissions, watchPermissions } from '@/state/permissions';
import { settingsStore, useSettings, type Settings } from '@/state/settings';
import { colors } from '@/theme/colors';

export default function SettingsScreen() {
  const ready = useSettings((s) => s.ready);
  const address = useSettings((s) => s.address);
  const [refreshing, setRefreshing] = useState(false);
  const previewing = useLive((s) => s.preview !== null);

  async function onRefresh() {
    setRefreshing(true);
    await refreshPermissions();
    setRefreshing(false);
  }

  return (
    <Screen
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => void onRefresh()}
          tintColor={colors.foreground}
          colors={[colors.primaryForeground]}
          progressBackgroundColor={colors.primary}
        />
      }
    >
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
          {previewing ? (
            <Button label={strings.settings.stopTest} icon="stop-circle" variant="secondary" style={styles.flex} onPress={stopTestAlert} />
          ) : (
            <Button label={strings.settings.testWarning} icon="alarm-light" variant="secondary" style={styles.flex} onPress={() => runTestAlert('warning')} />
          )}
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

type PermissionRow = {
  key: string;
  icon: IconName;
  label: string;
  /** null = unknown (Android doesn't tell apps, e.g. DND access) */
  ok: boolean | null;
  note?: string;
  action: () => Promise<unknown>;
};

function Permissions() {
  const state = usePermissions((s) => s.value);
  const checking = usePermissions((s) => s.checking);
  // Rows whose Android page was opened: they get a small refresh button next to "Open".
  const [opened, setOpened] = useState<ReadonlySet<string>>(() => new Set());

  useEffect(watchPermissions, []);
  useFocusEffect(
    useCallback(() => {
      void refreshPermissions();
    }, []),
  );

  const rows: PermissionRow[] = [
    { key: 'notifications', icon: 'bell-ring', label: strings.settings.notifications, ok: state?.notifications ?? null, action: allowNotifications },
    { key: 'fullScreen', icon: 'cellphone-lock', label: strings.settings.fullScreen, ok: state?.fullScreen ?? null, action: openFullScreenSettings },
    { key: 'battery', icon: 'battery-heart-variant', label: strings.settings.battery, ok: state?.batteryUnrestricted ?? null, action: openBatterySettings },
    { key: 'dnd', icon: 'minus-circle-off-outline', label: strings.settings.dnd, ok: null, note: strings.settings.dndNote, action: openDndSettings },
  ];

  async function open(row: PermissionRow) {
    setOpened((prev) => new Set(prev).add(row.key));
    await row.action().catch((e: unknown) => console.warn(`[settings] open ${row.key}`, e));
    await refreshPermissions(); // the Android page was closed again (startActivityAsync waits for it)
  }

  return (
    <>
      <SectionLabel>{strings.settings.permissions}</SectionLabel>
      <Card style={styles.tightCard}>
        <Txt size="sm" tone="muted">
          {strings.settings.permissionsHint}
        </Txt>
        {rows.map((r) => (
          <View key={r.key} style={styles.permRow}>
            <Icon name={r.icon} size={20} color={colors.muted} />
            <View style={styles.flex}>
              <Txt>{r.label}</Txt>
              {r.note ? (
                <Txt size="xs" tone="subtle">
                  {r.note}
                </Txt>
              ) : null}
            </View>
            {r.ok ? (
              <Icon name="check-circle" size={22} color={colors.ok} />
            ) : (
              <>
                {opened.has(r.key) && r.ok !== null ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={strings.settings.recheck}
                    hitSlop={10}
                    disabled={checking}
                    onPress={() => void refreshPermissions()}
                    style={styles.recheck}
                  >
                    {checking ? <ActivityIndicator size="small" color={colors.muted} /> : <Icon name="refresh" size={20} color={colors.muted} />}
                  </Pressable>
                ) : null}
                <Button label={r.ok === false ? strings.settings.allow : strings.settings.open} variant="secondary" onPress={() => void open(r)} />
              </>
            )}
          </View>
        ))}
        <Button label={strings.settings.appInfo} icon="cog-outline" variant="ghost" onPress={() => void openAppSettings()} />
      </Card>
    </>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  permRow: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 52 },
  recheck: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  tightCard: { gap: 4 },
});
