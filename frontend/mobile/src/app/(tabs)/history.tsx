import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, RefreshControl, StyleSheet, View } from 'react-native';

import { api } from '@/api/client';
import type { TripSummary } from '@/api/types';
import { ScoreBadge } from '@/components/dashboard';
import { Banner, Card, Icon, Pill, Screen, ScreenHeader, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { errorText, formatDateTime, formatDuration } from '@/lib/format';
import { useSettings } from '@/state/settings';
import { colors, radius } from '@/theme/colors';

/** My trips (GET /trips with the login token), newest first. The badge is the average score while driving. */
export default function HistoryScreen() {
  const address = useSettings((s) => s.serverAddress);
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const list = await api.listTrips(address);
      setTrips([...list].reverse()); // backend returns oldest → newest
      setError(null);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setRefreshing(false);
    }
  }, [address]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  return (
    <Screen
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => void load()} tintColor={colors.foreground} colors={[colors.primaryForeground]} progressBackgroundColor={colors.primary} />
      }>
      <ScreenHeader title={strings.history.title} subtitle={strings.history.subtitle} />
      {error ? <Banner icon="lan-disconnect" text={error} color={colors.destructive} /> : null}
      {trips && trips.length === 0 ? (
        <Card>
          <Txt tone="muted">{strings.history.empty}</Txt>
        </Card>
      ) : null}
      {trips?.map((trip) => (
        <Pressable
          key={trip.trip_id}
          onPress={() => router.push(`/trip/${trip.trip_id}`)}
          android_ripple={{ color: 'rgba(255,255,255,0.08)' }}
          style={styles.row}>
          <ScoreBadge score={trip.average_score} level={trip.level} />
          <View style={styles.flex}>
            <Txt weight="700">{formatDateTime(trip.started_at)}</Txt>
            <Txt size="sm" tone="muted">
              {formatDuration(trip.duration_s)} ·{' '}
              {trip.behaviors.length ? strings.history.issues(trip.behaviors.length) : strings.history.clean}
            </Txt>
          </View>
          {trip.status === 'active' ? (
            <Pill label={strings.history.active} color={colors.ok} />
          ) : (
            <Icon name="chevron-right" size={22} color={colors.subtle} />
          )}
        </Pressable>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    padding: 14,
    borderRadius: radius.lg,
    backgroundColor: colors.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    overflow: 'hidden',
  },
});
