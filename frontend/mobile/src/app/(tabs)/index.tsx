import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { ensureNotificationPermission } from '@/alerts/notifications';
import { api } from '@/api/client';
import type { TripState, TripSummary } from '@/api/types';
import { BehaviorGrid, Indicators, Lamp, LevelBar, ScoreBadge, StatusPill } from '@/components/dashboard';
import { Banner, Button, Card, Screen, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { useNow } from '@/hooks/useNow';
import { errorText, formatDuration } from '@/lib/format';
import { setActiveTrip, setEndedTrip, useLive } from '@/state/live';
import { useProfile } from '@/state/profile';
import { useSettings } from '@/state/settings';
import { colors, lampColors, withAlpha } from '@/theme/colors';

const KEEP_AWAKE_TAG = 'drive';
const STALE_AFTER_MS = 3000;

export default function DriveScreen() {
  const status = useLive((s) => s.status);
  const trip = useLive((s) => s.trip);
  const lastMessageAt = useLive((s) => s.lastMessageAt);
  const summary = useLive((s) => s.summary);
  const address = useSettings((s) => s.address);
  const keepAwake = useSettings((s) => s.keepAwake);
  const driverId = useProfile((p) => p.driverId);
  const driverName = useProfile((p) => p.name);
  const contactName = useProfile((p) => p.contactName);
  const contactPhone = useProfile((p) => p.contactPhone);
  const now = useNow(1000);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tripActive = trip !== null;
  useEffect(() => {
    if (!tripActive || !keepAwake) return;
    void activateKeepAwakeAsync(KEEP_AWAKE_TAG);
    return () => {
      void deactivateKeepAwake(KEEP_AWAKE_TAG);
    };
  }, [tripActive, keepAwake]);

  async function startTrip() {
    if (!driverId) {
      router.push('/profile');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await ensureNotificationPermission();
      const state = await api.startTrip(address, {
        driver_id: driverId,
        emergency_contact: contactPhone
          ? { name: contactName || strings.profile.contactFallback, phone: contactPhone }
          : null,
      });
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
      const ended = await api.endTrip(address, tripId);
      setEndedTrip(ended);
      router.push(`/trip/${tripId}`);
    } catch (e) {
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
      ) : status === 'open' ? (
        <Ready
          driverId={driverId}
          driverName={driverName}
          summary={summary}
          busy={busy}
          onStart={() => void startTrip()}
        />
      ) : (
        <Offline address={address} />
      )}
    </Screen>
  );
}

function ActiveTrip({ trip, stale, busy, onEnd }: { trip: TripState; stale: boolean; busy: boolean; onEnd: () => void }) {
  const light = lampColors[trip.response.dashboard_light];
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
      <Indicators response={trip.response} stale={stale} />
      <Txt size="xs" tone="subtle" style={styles.center}>
        {strings.drive.driver}: {trip.driver_id} · trip {trip.trip_id.slice(0, 8)}
      </Txt>
      <Button label={strings.drive.endTrip} icon="flag-checkered" variant="danger" loading={busy} onPress={onEnd} />
    </View>
  );
}

function Ready({
  driverId,
  driverName,
  summary,
  busy,
  onStart,
}: {
  driverId: string;
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
        <Txt tone="muted">{driverId ? strings.drive.readyBody : strings.drive.noProfile}</Txt>
        {driverId ? (
          <Txt size="sm" tone="subtle">
            {strings.drive.driver}: {driverName || driverId} ({driverId})
          </Txt>
        ) : null}
        <Button
          big
          label={driverId ? strings.drive.startTrip : strings.drive.goToProfile}
          icon={driverId ? 'play-circle' : 'account-circle'}
          loading={busy}
          onPress={onStart}
        />
      </Card>
      {summary ? (
        <Card>
          <Txt size="xs" tone="subtle" weight="800" style={styles.kicker}>
            {strings.drive.lastTrip.toUpperCase()}
          </Txt>
          <View style={styles.row}>
            <ScoreBadge score={summary.final_score} level={summary.level} />
            <View style={styles.flex}>
              <Txt weight="700">{strings.levels[summary.level]}</Txt>
              <Txt size="sm" tone="muted">
                {formatDuration(summary.duration_s)} · {summary.driver_id}
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

function Offline({ address }: { address: string }) {
  return (
    <Card>
      <View style={styles.row}>
        <Txt size="lg" weight="800" style={styles.flex}>
          {strings.drive.offlineTitle}
        </Txt>
      </View>
      <Txt tone="muted">{strings.drive.offlineBody(address)}</Txt>
      <Button
        label={strings.drive.openSettings}
        icon="lan-connect"
        variant="secondary"
        onPress={() => router.push('/settings')}
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
});
