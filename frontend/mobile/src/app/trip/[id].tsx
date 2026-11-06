import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, StyleSheet, View } from 'react-native';

import { api } from '@/api/client';
import type { DangerMoment, TripReport, TripSummary } from '@/api/types';
import { ScoreBadge } from '@/components/dashboard';
import { ChartLegend, DriveChart, MomentList, MomentSheet } from '@/components/report';
import { Banner, Card, Icon, Screen, SectionLabel, Txt } from '@/components/ui';
import { behaviorMeta } from '@/config/behaviors';
import { strings } from '@/config/strings';
import { errorText, formatDateTime, formatDuration, formatScore } from '@/lib/format';
import { useLive } from '@/state/live';
import { useSettings } from '@/state/settings';
import { colors, levelColors } from '@/theme/colors';

type ReportState = { status: 'loading' } | { status: 'ok'; report: TripReport } | { status: 'unavailable' };

export default function TripSummaryScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const address = useSettings((s) => s.address);
  const cached = useLive((s) => (s.summary?.trip_id === id ? s.summary : null));
  const [fetched, setFetched] = useState<TripSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ReportState>({ status: 'loading' });
  const [refreshing, setRefreshing] = useState(false);
  const [selected, setSelected] = useState<DangerMoment | null>(null);

  // The report (server: sections + moments) has the summary too; the plain summary is the fallback.
  const fetchAll = useCallback(() => Promise.allSettled([api.getSummary(address, id), api.getReport(address, id)]), [address, id]);
  const apply = useCallback(([summary, full]: Awaited<ReturnType<typeof fetchAll>>) => {
    if (summary.status === 'fulfilled') setFetched(summary.value);
    else if (full.status === 'rejected') setError(errorText(summary.reason));
    setReport(full.status === 'fulfilled' ? { status: 'ok', report: full.value } : { status: 'unavailable' });
  }, []);

  useEffect(() => {
    let cancelled = false;
    void fetchAll().then((results) => {
      if (!cancelled) apply(results);
    });
    return () => {
      cancelled = true;
    };
  }, [fetchAll, apply]);

  async function refresh() {
    setRefreshing(true);
    apply(await fetchAll());
    setRefreshing(false);
  }

  const summary = (report.status === 'ok' ? report.report.trip : null) ?? fetched ?? cached;
  const refreshControl = (
    <RefreshControl
      refreshing={refreshing}
      onRefresh={() => void refresh()}
      tintColor={colors.foreground}
      colors={[colors.primaryForeground]}
      progressBackgroundColor={colors.primary}
    />
  );

  if (!summary) {
    return (
      <Screen refreshControl={refreshControl}>
        {error ? <Banner icon="alert-circle-outline" text={error} color={colors.destructive} /> : <ActivityIndicator color={colors.foreground} />}
      </Screen>
    );
  }

  const color = levelColors[summary.level];
  return (
    <Screen refreshControl={refreshControl}>
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

      <DriveReport state={report} live={summary.status === 'active'} onSelect={setSelected} />

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
      <MomentSheet moment={selected} onClose={() => setSelected(null)} />
    </Screen>
  );
}

function DriveReport({ state, live, onSelect }: { state: ReportState; live: boolean; onSelect: (m: DangerMoment) => void }) {
  if (state.status === 'loading') {
    return (
      <Card style={styles.reportCard}>
        <Txt size="sm" tone="muted">
          {strings.report.loading}
        </Txt>
      </Card>
    );
  }
  if (state.status === 'unavailable') {
    return <Banner icon="chart-line-variant" text={strings.report.unavailable} color={colors.subtle} />;
  }
  const { sections, moments } = state.report;
  return (
    <>
      <SectionLabel>{strings.report.title}</SectionLabel>
      <Card style={styles.reportCard}>
        {sections.length ? (
          <>
            <DriveChart sections={sections} moments={moments} onSelect={onSelect} />
            <ChartLegend />
            <Txt size="xs" tone="subtle">
              {live ? strings.report.live : strings.report.hint}
            </Txt>
          </>
        ) : (
          <Txt size="sm" tone="muted">
            {strings.report.empty}
          </Txt>
        )}
      </Card>
      {sections.length ? (
        <>
          <SectionLabel>{strings.report.moments}</SectionLabel>
          {moments.length ? (
            <MomentList moments={moments} onSelect={onSelect} />
          ) : (
            <Banner icon="shield-check" text={strings.report.noMoments} color={colors.ok} />
          )}
        </>
      ) : null}
    </>
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
  reportCard: { gap: 10, paddingHorizontal: 10 },
});
