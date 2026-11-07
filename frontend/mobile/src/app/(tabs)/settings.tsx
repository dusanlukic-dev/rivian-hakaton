import Constants from 'expo-constants';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { RefreshControl, StyleSheet, View } from 'react-native';

import {
  allowNotifications,
  openAppSettings,
  openBatterySettings,
  openDndSettings,
  openFullScreenSettings,
} from '@/alerts/notifications';
import { api } from '@/api/client';
import { StatusPill } from '@/components/dashboard';
import { ServerStatusPill } from '@/components/server';
import {
  Button,
  Card,
  Chevron,
  Divider,
  Icon,
  ListRow,
  Pill,
  Screen,
  ScreenHeader,
  SectionLabel,
  ToggleRow,
  Txt,
  type IconName,
} from '@/components/ui';
import { strings } from '@/config/strings';
import { runTestAlert, stopTestAlert, useLive } from '@/state/live';
import { refreshPermissions, usePermissions, watchPermissions } from '@/state/permissions';
import { settingsStore, useSettings, type AlertToggle } from '@/state/settings';
import { colors } from '@/theme/colors';

export default function SettingsScreen() {
  const address = useSettings((s) => s.address);
  const bluetooth = useSettings((s) => s.carLink === 'bluetooth');
  const carName = useSettings((s) => s.carName);
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
      }>
      <ScreenHeader title={strings.settings.title} />

      <SectionLabel>{strings.settings.connection}</SectionLabel>
      <Card flush>
        <ListRow
          icon={bluetooth ? 'bluetooth' : 'car-connected'}
          title={bluetooth ? (carName ?? strings.carLink.bluetooth) : address}
          subtitle={bluetooth ? strings.settings.connectionBluetooth : strings.settings.connectionWifi}
          right={
            <View style={styles.rowEnd}>
              <StatusPill />
              <Chevron />
            </View>
          }
          onPress={() => router.push('/connection')}
        />
      </Card>

      <ServerSection />

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

      <PhoneSetup />

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

/** The server (accounts, history, drive reports): its address and whether it answers. Opens the Server screen. */
function ServerSection() {
  const serverAddress = useSettings((s) => s.serverAddress);

  // Fresh reachability for the pill whenever Settings opens. Silent: the pill keeps its last value until the answer.
  useFocusEffect(
    useCallback(() => {
      api.serverHealth(serverAddress).catch(() => {});
    }, [serverAddress]),
  );

  return (
    <>
      <SectionLabel>{strings.settings.server}</SectionLabel>
      <Card flush>
        <ListRow
          icon="server-network"
          title={serverAddress}
          subtitle={strings.settings.serverRow}
          right={
            <View style={styles.rowEnd}>
              <ServerStatusPill address={serverAddress} />
              <Chevron />
            </View>
          }
          onPress={() => router.push('/server')}
        />
      </Card>
    </>
  );
}

const TOGGLES: { key: AlertToggle; icon: IconName; label: string }[] = [
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

type Access = {
  key: string;
  icon: IconName;
  label: string;
  hint: string;
  /** null = not known yet (first check running) */
  ok: boolean | null;
  open: () => Promise<unknown>;
};

/**
 * Android special access the alerts need. Every row works the same way: a green "On" when Android reports it, an
 * "Allow" button otherwise. Each state is re-read when Android's page closes and whenever the app comes back.
 */
function PhoneSetup() {
  const state = usePermissions((s) => s.value);

  useEffect(watchPermissions, []);
  useFocusEffect(
    useCallback(() => {
      void refreshPermissions();
    }, []),
  );

  const rows: Access[] = [
    { key: 'notifications', icon: 'bell-ring', label: strings.settings.notifications, hint: strings.settings.notificationsHint, ok: state?.notifications ?? null, open: allowNotifications },
    { key: 'fullScreen', icon: 'cellphone-lock', label: strings.settings.fullScreen, hint: strings.settings.fullScreenHint, ok: state?.fullScreen ?? null, open: openFullScreenSettings },
    { key: 'battery', icon: 'battery-heart-variant', label: strings.settings.battery, hint: strings.settings.batteryHint, ok: state?.batteryUnrestricted ?? null, open: openBatterySettings },
    { key: 'dnd', icon: 'minus-circle-off-outline', label: strings.settings.dnd, hint: strings.settings.dndHint, ok: state?.dnd ?? null, open: openDndSettings },
  ];
  const known = state !== null;
  const ready = rows.filter((r) => r.ok === true).length;
  const done = ready === rows.length;

  async function allow(row: Access) {
    await row.open().catch((e: unknown) => console.warn(`[settings] open ${row.key}`, e));
    await refreshPermissions(); // Android's page was closed again (startActivityAsync waits for it)
  }

  return (
    <>
      <SectionLabel>{strings.settings.permissions}</SectionLabel>
      <Card flush>
        <View style={styles.setupHead}>
          <Txt size="sm" tone="muted" style={styles.flex}>
            {strings.settings.permissionsHint}
          </Txt>
          {known ? (
            <Pill
              label={done ? strings.settings.permissionsDone : strings.settings.permissionsCount(ready, rows.length)}
              color={done ? colors.ok : colors.warn}
            />
          ) : null}
        </View>
        {rows.map((r, i) => (
          <View key={r.key}>
            <Divider inset={i > 0} />
            <ListRow
              icon={r.icon}
              iconColor={r.ok ? colors.ok : colors.muted}
              title={r.label}
              subtitle={r.hint}
              right={
                r.ok === null ? null : r.ok ? (
                  <View style={styles.granted}>
                    <Icon name="check-circle" size={18} color={colors.ok} />
                    <Txt size="sm" weight="700" style={styles.grantedText}>
                      {strings.settings.granted}
                    </Txt>
                  </View>
                ) : (
                  <Button size="sm" label={strings.settings.allow} onPress={() => void allow(r)} />
                )
              }
            />
          </View>
        ))}
        <Divider inset={false} />
        <View style={styles.setupFoot}>
          <Button label={strings.settings.systemSettings} icon="open-in-new" onPress={() => void openAppSettings()} />
        </View>
      </Card>
    </>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  rowEnd: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  tightCard: { gap: 4 },
  setupHead: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16 },
  setupFoot: { padding: 16 },
  granted: { flexDirection: 'row', alignItems: 'center', gap: 4, minWidth: 56, justifyContent: 'flex-end' },
  grantedText: { color: colors.ok },
});
