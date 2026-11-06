import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { api } from '@/api/client';
import type { TripSummary } from '@/api/types';
import { ScoreBadge } from '@/components/dashboard';
import { Banner, Card, Icon, Screen, SectionLabel, Txt } from '@/components/ui';
import { behaviorMeta } from '@/config/behaviors';
import { strings } from '@/config/strings';
import { errorText, formatDateTime, formatDuration, formatScore } from '@/lib/format';
import { useLive } from '@/state/live';
import { useSettings } from '@/state/settings';
import { colors, levelColors } from '@/theme/colors';

export default function TripSummaryScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const address = useSettings((s) => s.address);
  const cached = useLive((s) => (s.summary?.trip_id === id ? s.summary : null));
  const [fetched, setFetched] = useState<TripSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getSummary(address, id)
      .then((summary) => !cancelled && setFetched(summary))
      .catch((e: unknown) => !cancelled && setError(errorText(e)));
    return () => {
      cancelled = true;
    };
  }, [address, id]);

  const summary = fetched ?? cached;

  if (!summary) {
    return (
      <Screen>
        {error ? <Banner icon="alert-circle-outline" text={error} color={colors.destructive} /> : <ActivityIndicator color={colors.foreground} />}
      </Screen>
    );
  }

  const color = levelColors[summary.level];
  return (
    <Screen>
      <View style={styles.hero}>
        <ScoreBadge score={summary.final_score} level={summary.level} size={132} />
        <Txt size="lg" weight="800" style={{ color }}>
          {strings.levels[summary.level]}
        </Txt>
        <Txt size="sm" tone="muted">
          {strings.summary.final} · {summary.driver_id}
        </Txt>
      </View>

      <View style={styles.stats}>
        <Stat label={strings.summary.average} value={formatScore(summary.average_score)} />
        <Stat label={strings.summary.minimum} value={formatScore(summary.min_score)} />
        <Stat label={strings.summary.duration} value={formatDuration(summary.duration_s)} />
      </View>
      <Txt size="sm" tone="subtle" style={styles.center}>
        {strings.summary.started} {formatDateTime(summary.started_at)}
      </Txt>

      {summary.emergency_alert_sent ? (
        <Banner icon="alert-octagon" text={strings.summary.emergency} color={colors.alarm} />
      ) : null}

      {summary.behaviors.length === 0 ? (
        <Banner icon="check-circle" text={strings.summary.clean} color={colors.ok} />
      ) : (
        <>
          <SectionLabel>{strings.summary.behaviours}</SectionLabel>
          {summary.behaviors.map((b) => {
            const meta = behaviorMeta(b.behavior);
            return (
              <Card key={b.behavior}>
                <View style={styles.row}>
                  <Icon name={meta.icon} size={26} color={colors.alarm} />
                  <View style={styles.flex}>
                    <Txt weight="700">{meta.label}</Txt>
                    <Txt size="sm" tone="muted">
                      {strings.summary.times(b.occurrences)} · {b.total_seconds.toFixed(0)} s
                    </Txt>
                  </View>
                </View>
                <Txt size="sm">{b.tip}</Txt>
              </Card>
            );
          })}
        </>
      )}
    </Screen>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card style={styles.stat}>
      <Txt size="xl">{value}</Txt>
      <Txt size="xs" tone="subtle" weight="700">
        {label.toUpperCase()}
      </Txt>
    </Card>
  );
}

const styles = StyleSheet.create({
  hero: { alignItems: 'center', gap: 8, paddingVertical: 12 },
  stats: { flexDirection: 'row', gap: 8 },
  stat: { flex: 1, alignItems: 'center', gap: 2, padding: 12 },
  center: { textAlign: 'center' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  flex: { flex: 1 },
});
