import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { ensureNotificationPermission, openAppSettings, openBluetoothSettings } from '@/alerts/notifications';
import { requestCarLinkPermission } from '@/api/carlink';
import { ApiError, api } from '@/api/client';
import type { TripState, TripSummary } from '@/api/types';
import { BehaviorGrid, Indicators, Lamp, LevelBar, ScoreBadge, StatusPill } from '@/components/dashboard';
import { RecentSections } from '@/components/report';
import { Banner, Button, Card, Screen, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { useNow } from '@/hooks/useNow';
import { errorText, formatDuration } from '@/lib/format';
import { dropTrip, reconnectCar, retryCarLink, setActiveTrip, setEndedTrip, useLive } from '@/state/live';
import { useAuth } from '@/state/auth';
import { useSettings } from '@/state/settings';
import { colors, lampColors, withAlpha } from '@/theme/colors';

const KEEP_AWAKE_TAG = 'drive';
const STALE_AFTER_MS = 3000;

export default function DriveScreen() {
  const link = useLive((s) => s.link);
  const trip = useLive((s) => s.trip);
  const lastMessageAt = useLive((s) => s.lastMessageAt);
  const summary = useLive((s) => s.summary);
  const address = useSettings((s) => s.address);
  const carLink = useSettings((s) => s.carLink);
  const keepAwake = useSettings((s) => s.keepAwake);
  const driverName = useAuth((a) => a.user?.display_name ?? '');
  const now = useNow(1000);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tripActive = trip !== null;
  useEffect(() => {
    if (!tripActive || !keepAwake) return;
    // Both need the Activity. Swiping the app away during a trip unmounts this screen after Android
    // destroyed the Activity (the foreground service keeps JS alive), and the call then rejects.
    activateKeepAwakeAsync(KEEP_AWAKE_TAG).catch(() => {});
    return () => {
      deactivateKeepAwake(KEEP_AWAKE_TAG).catch(() => {});
    };
  }, [tripActive, keepAwake]);

  async function startTrip() {
    setBusy(true);
    setError(null);
    try {
      await ensureNotificationPermission();
      // Logged in: the trip belongs to the account, and the account's emergency contact is used.
      const state = await api.startTrip();
      setActiveTrip(state);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function endTrip(tripId: string) {
    setBusy(true);
    setError(null);
    try {
      const ended = await api.endTrip(tripId);
      setEndedTrip(ended);
      router.push(`/trip/${tripId}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        // The car no longer runs it (backend restarted); the server closed it, so show what it stored.
        dropTrip(tripId);
        router.push(`/trip/${tripId}`);
        return;
      }
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <View style={styles.header}>
        <View style={styles.flex}>
          <Txt size="xs" tone="subtle" weight="800" style={styles.kicker}>
            {strings.appName.toUpperCase()}
          </Txt>
          <Txt size="xl">{trip ? strings.drive.onTrip : strings.tabs.drive}</Txt>
        </View>
        <StatusPill />
      </View>

      {error ? <Banner icon="alert-circle-outline" text={error} color={colors.destructive} /> : null}

      {trip ? (
        <ActiveTrip
          trip={trip}
          stale={now - lastMessageAt > STALE_AFTER_MS}
          busy={busy}
          onEnd={() => void endTrip(trip.trip_id)}
        />
      ) : link === 'online' ? (
        <Ready
          driverName={driverName}
          summary={summary}
          busy={busy}
          onStart={() => void startTrip()}
        />
      ) : link === 'checking' ? (
        <Connecting />
      ) : carLink === 'bluetooth' ? (
        <CarLinkCard />
      ) : (
        <Offline address={address} />
      )}
    </Screen>
  );
}

function ActiveTrip({ trip, stale, busy, onEnd }: { trip: TripState; stale: boolean; busy: boolean; onEnd: () => void }) {
  const light = lampColors[trip.response.dashboard_light];
  const sections = useLive((s) => s.sections);
  const focused = Object.keys(trip.active_behaviors).length === 0;
  return (
    <View style={styles.stack}>
      <View style={styles.lampWrap}>
        <Lamp light={trip.response.dashboard_light} score={trip.score} level={trip.level} />
      </View>
      <LevelBar level={trip.level} />
      <Card style={{ borderColor: withAlpha(light, 0.55) }}>
        <Txt size="lg" weight="700" style={styles.center}>
          {trip.response.message}
        </Txt>
        {focused ? (
          <Txt size="sm" tone="muted" style={styles.center}>
            {strings.drive.focused}
          </Txt>
        ) : null}
      </Card>
      {stale ? <Banner icon="wifi-off" text={strings.drive.staleBanner} /> : null}
      <BehaviorGrid active={trip.active_behaviors} />
      <RecentSections sections={sections.filter((s) => s.trip_id === trip.trip_id)} />
      <Indicators response={trip.response} stale={stale} />
      <Txt size="xs" tone="subtle" style={styles.center}>
        {strings.drive.driver}: {trip.driver_id} · trip {trip.trip_id.slice(0, 8)}
      </Txt>
      <Button label={strings.drive.endTrip} icon="flag-checkered" variant="danger" loading={busy} onPress={onEnd} />
    </View>
  );
}

function Ready({
  driverName,
  summary,
  busy,
  onStart,
}: {
  driverName: string;
  summary: TripSummary | null;
  busy: boolean;
  onStart: () => void;
}) {
  return (
    <View style={styles.stack}>
      <Card>
        <Txt size="lg" weight="800">
          {strings.drive.readyTitle}
        </Txt>
        <Txt tone="muted">{strings.drive.readyBody}</Txt>
        {driverName ? (
          <Txt size="sm" tone="subtle">
            {strings.drive.drivingAs(driverName)}
          </Txt>
        ) : null}
        <Button size="lg" label={strings.drive.startTrip} icon="play-circle" loading={busy} onPress={onStart} />
      </Card>
      {summary ? (
        <Card>
          <Txt size="xs" tone="subtle" weight="800" style={styles.kicker}>
            {strings.drive.lastTrip.toUpperCase()}
          </Txt>
          <View style={styles.row}>
            <ScoreBadge score={summary.average_score} level={summary.level} />
            <View style={styles.flex}>
              <Txt weight="700">{strings.levels[summary.level]}</Txt>
              <Txt size="sm" tone="muted">
                {formatDuration(summary.duration_s)} · {strings.summary.headline.toLowerCase()}
              </Txt>
            </View>
          </View>
          <Button
            label={strings.drive.viewSummary}
            variant="secondary"
            icon="chart-box-outline"
            onPress={() => router.push(`/trip/${summary.trip_id}`)}
          />
        </Card>
      ) : null}
    </View>
  );
}

/** First connection attempt still running (a slow network at start-up): calm, no "offline" scare. */
function Connecting() {
  return (
    <Card>
      <View style={styles.row}>
        <ActivityIndicator color={colors.muted} />
        <Txt size="lg" weight="800" style={styles.flex}>
          {strings.drive.connectingTitle}
        </Txt>
      </View>
      <Txt tone="muted">{strings.drive.connectingBody}</Txt>
    </Card>
  );
}

/** The Bluetooth link isn't up: say why, and offer the one action that fixes it. */
function CarLinkCard() {
  const phase = useLive((s) => s.carLink?.phase ?? 'choose');
  const carName = useSettings((s) => s.carName);
  const paused = useSettings((s) => s.carDeviceId !== null && !s.carAuto);
  const [blocked, setBlocked] = useState(false);
  const copy = strings.carLink.card[phase];

  async function allow() {
    const result = await requestCarLinkPermission();
    if (result === 'blocked') setBlocked(true);
    retryCarLink();
  }

  return (
    <Card>
      <View style={styles.row}>
        {phase === 'searching' || phase === 'connecting' ? <ActivityIndicator color={colors.muted} /> : null}
        <Txt size="lg" weight="800" style={styles.flex}>
          {copy.title}
        </Txt>
      </View>
      <Txt tone="muted">{blocked ? strings.carLink.blocked : copy.body}</Txt>
      {phase === 'no-permission' ? (
        blocked ? (
          <Button label={strings.carLink.openAppSettings} icon="open-in-new" onPress={() => void openAppSettings()} />
        ) : (
          <Button label={strings.carLink.allow} icon="bluetooth" onPress={() => void allow()} />
        )
      ) : phase === 'off' ? (
        <Button label={strings.carLink.openBluetooth} icon="bluetooth-settings" onPress={() => void openBluetoothSettings()} />
      ) : phase === 'choose' ? (
        paused ? (
          <Button label={strings.carLink.connectTo(carName ?? strings.carLink.yourCar)} icon="bluetooth-connect" onPress={reconnectCar} />
        ) : (
          <Button label={strings.carLink.chooseCar} icon="bluetooth-connect" onPress={() => router.push('/connection')} />
        )
      ) : (
        <View style={styles.buttons}>
          <Button label={strings.carLink.searchAgain} icon="bluetooth-connect" variant="secondary" style={styles.flex} onPress={retryCarLink} />
          <Button label={strings.drive.openSettings} icon="cog-outline" variant="secondary" style={styles.flex} onPress={() => router.push('/connection')} />
        </View>
      )}
    </Card>
  );
}

function Offline({ address }: { address: string }) {
  return (
    <Card>
      <Txt size="lg" weight="800">
        {strings.drive.offlineTitle}
      </Txt>
      <Txt tone="muted">{strings.drive.offlineBody(address)}</Txt>
      <Button
        label={strings.drive.openSettings}
        icon="lan-connect"
        variant="secondary"
        onPress={() => router.push('/connection')}
      />
    </Card>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  kicker: { letterSpacing: 1.4 },
  flex: { flex: 1 },
  stack: { gap: 14 },
  lampWrap: { alignItems: 'center', paddingVertical: 12 },
  center: { textAlign: 'center' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  buttons: { flexDirection: 'row', alignItems: 'center', gap: 8 },
});
