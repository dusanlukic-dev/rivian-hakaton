import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { api } from '@/api/client';
import type { TripSummary } from '@/api/types';
import { behaviorMeta } from '@/config/behaviors';
import { strings } from '@/config/strings';
import { errorText, formatDate, formatDateTime, formatDuration, formatScore } from '@/lib/format';
import {
  computeTrends,
  MIN_TREND_TRIPS,
  MIN_TRIP_S,
  TREND_WINDOWS,
  type BehaviorDirection,
  type BehaviorTrend,
  type Direction,
  type Trends,
  type TrendWindow,
} from '@/lib/trends';
import { useSettings } from '@/state/settings';
import { colors, levelColors, radius, withAlpha } from '@/theme/colors';

import { Button, Card, Icon, Txt, type IconName } from './ui';

const CHART_H = 96;
const GRID = [100, 75, 50];

const DIRECTION_STYLE: Record<Direction, { icon: IconName; color: string }> = {
  better: { icon: 'trending-up', color: colors.ok },
  worse: { icon: 'trending-down', color: colors.alarm },
  steady: { icon: 'trending-neutral', color: colors.muted },
};

const BEHAVIOR_DIRECTION_STYLE: Record<BehaviorDirection, { icon: IconName; color: string }> = {
  fewer: { icon: 'arrow-down', color: colors.ok },
  more: { icon: 'arrow-up', color: colors.warn },
  same: { icon: 'minus', color: colors.subtle },
  new: { icon: 'arrow-up', color: colors.warn },
};

/**
 * Drive screen: how the driver's recent trips are trending (GET /trips, my trips). Reloads whenever the screen gets
 * focus (ending a trip opens its summary, so coming back reloads). Short test trips are filtered out (lib/trends.ts).
 */
export function TrendsCard() {
  const address = useSettings((s) => s.serverAddress);
  const [all, setAll] = useState<TripSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<TrendWindow>('last10');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setAll(await api.listTrips(address));
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, [address]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  if (all === null) {
    return (
      <Card>
        <Header range={range} onRange={setRange} />
        {error ? (
          <Txt size="sm" tone="muted">
            {strings.trends.unavailable}
          </Txt>
        ) : (
          <View style={styles.row}>
            <ActivityIndicator color={colors.muted} />
            <Txt size="sm" tone="muted">
              {strings.trends.loading}
            </Txt>
          </View>
        )}
      </Card>
    );
  }

  const trends = computeTrends(all, range);
  const selected = trends?.trips.find((t) => t.trip_id === selectedId) ?? null;

  return (
    <Card>
      <Header range={range} onRange={setRange} />
      {trends === null ? (
        <Txt tone="muted">{range === 'month' && all.length > 0 ? strings.trends.emptyWindow : strings.trends.empty}</Txt>
      ) : (
        <>
          <Txt size="sm" tone="muted">
            {strings.trends.range(
              trends.trips.length,
              formatDate(trends.trips[0].started_at),
              formatDate(trends.trips[trends.trips.length - 1].started_at),
            )}
          </Txt>
          <Headline trends={trends} />
          <TripBars
            trips={trends.trips}
            selectedId={selected?.trip_id ?? null}
            onSelect={(id) => setSelectedId(id === selectedId ? null : id)}
          />
          {selected ? (
            <Pressable
              accessibilityRole="button"
              onPress={() => router.push(`/trip/${selected.trip_id}`)}
              android_ripple={{ color: 'rgba(255,255,255,0.08)' }}
              style={styles.selected}>
              <View style={[styles.dot, { backgroundColor: levelColors[selected.level] }]} />
              <View style={styles.flex}>
                <Txt size="sm" weight="700">
                  {strings.trends.openTrip(formatDateTime(selected.started_at), formatScore(selected.average_score))}
                </Txt>
                <Txt size="xs" tone="muted">
                  {strings.levels[selected.level]} · {formatDuration(selected.duration_s)}
                </Txt>
              </View>
              <Icon name="chevron-right" size={20} color={colors.subtle} />
            </Pressable>
          ) : (
            <Txt size="xs" tone="subtle">
              {strings.trends.chartHint}
            </Txt>
          )}
          <Stats trends={trends} />
          <Risks behaviors={trends.behaviors} />
          {trends.tip ? (
            <View style={styles.tip}>
              <Icon name="lightbulb-on-outline" size={18} color={colors.warn} />
              <Txt size="sm" style={styles.flex}>
                <Txt size="sm" weight="700">
                  {strings.trends.tip}:{' '}
                </Txt>
                {trends.tip}
              </Txt>
            </View>
          ) : null}
        </>
      )}
      {error ? (
        <Txt size="xs" tone="subtle">
          {strings.trends.unavailable}
        </Txt>
      ) : null}
      {trends && trends.shortLeftOut > 0 ? (
        <Txt size="xs" tone="subtle">
          {strings.trends.shortLeftOut(trends.shortLeftOut, MIN_TRIP_S)}
        </Txt>
      ) : null}
      {all.length > 0 ? (
        <Button
          label={strings.trends.allTrips}
          variant="secondary"
          icon="history"
          onPress={() => router.push('/history')}
        />
      ) : null}
    </Card>
  );
}

function Header({ range, onRange }: { range: TrendWindow; onRange: (w: TrendWindow) => void }) {
  return (
    <View style={styles.header}>
      <Txt size="xs" tone="subtle" weight="800" style={[styles.kicker, styles.flex]}>
        {strings.trends.title.toUpperCase()}
      </Txt>
      <View style={styles.chips}>
        {TREND_WINDOWS.map((w) => {
          const on = w === range;
          return (
            <Pressable
              key={w}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              onPress={() => onRange(w)}
              hitSlop={4}
              style={[styles.chip, on && styles.chipOn]}>
              <Txt size="xs" weight="700" tone={on ? 'inverse' : 'muted'}>
                {strings.trends.windows[w]}
              </Txt>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function Headline({ trends }: { trends: Trends }) {
  const d = trends.direction ? DIRECTION_STYLE[trends.direction] : null;
  return (
    <View style={styles.headline}>
      <View>
        <Txt size="xxl" style={styles.tabular}>
          {formatScore(trends.average)}
        </Txt>
        <Txt size="xs" tone="muted">
          {strings.trends.average}
        </Txt>
      </View>
      <View style={styles.flex}>
        {d && trends.direction && trends.delta !== null ? (
          <>
            <View style={styles.row}>
              <Icon name={d.icon} size={22} color={d.color} />
              <Txt weight="800" style={{ color: d.color }}>
                {trends.delta >= 0 ? '+' : '−'}
                {Math.abs(trends.delta).toFixed(1)} · {strings.trends.direction[trends.direction]}
              </Txt>
            </View>
            <Txt size="xs" tone="muted">
              {strings.trends.vsEarlier}
            </Txt>
          </>
        ) : (
          <Txt size="xs" tone="muted">
            {strings.trends.needMore(MIN_TREND_TRIPS)}
          </Txt>
        )}
      </View>
    </View>
  );
}

/** One bar per trip (average score), coloured by the level the backend gave that trip. */
function TripBars({
  trips,
  selectedId,
  onSelect,
}: {
  trips: TripSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <View style={styles.chart}>
      <View style={styles.axis}>
        {GRID.map((v) => (
          <Txt key={v} size="xs" tone="subtle" style={[styles.axisLabel, { top: (1 - v / 100) * CHART_H - 7 }]}>
            {v}
          </Txt>
        ))}
      </View>
      <View style={styles.plot}>
        {GRID.map((v) => (
          <View key={v} style={[styles.grid, { top: (1 - v / 100) * CHART_H }]} />
        ))}
        {trips.map((t) => {
          const dim = selectedId !== null && selectedId !== t.trip_id;
          return (
            <Pressable
              key={t.trip_id}
              accessibilityRole="button"
              accessibilityLabel={`${formatDateTime(t.started_at)}, ${formatScore(t.average_score)}, ${strings.levels[t.level]}`}
              onPress={() => onSelect(t.trip_id)}
              style={styles.column}>
              <View
                style={[
                  styles.bar,
                  {
                    height: Math.max(4, (Math.min(Math.max(t.average_score, 0), 100) / 100) * CHART_H),
                    backgroundColor: levelColors[t.level],
                    opacity: dim ? 0.3 : 1,
                  },
                ]}
              />
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.stat}>
      <Txt size="lg" weight="800" style={[styles.tabular, color ? { color } : null]}>
        {value}
      </Txt>
      <Txt size="xs" tone="muted" numberOfLines={1}>
        {label}
      </Txt>
    </View>
  );
}

function Stats({ trends }: { trends: Trends }) {
  return (
    <View style={styles.stats}>
      <Stat label={strings.trends.cleanTrips} value={`${trends.cleanTrips}/${trends.trips.length}`} />
      <Stat label={strings.trends.riskyMoments} value={String(trends.riskyMoments)} />
      <Stat label={strings.trends.driving} value={formatDuration(trends.drivingS)} />
      {trends.emergencies > 0 ? (
        <Stat label={strings.trends.emergencies} value={String(trends.emergencies)} color={colors.alarm} />
      ) : null}
    </View>
  );
}

function Risks({ behaviors }: { behaviors: BehaviorTrend[] }) {
  if (behaviors.length === 0) {
    return (
      <View style={styles.tip}>
        <Icon name="check-decagram-outline" size={18} color={colors.ok} />
        <Txt size="sm" style={styles.flex}>
          {strings.trends.noRisks}
        </Txt>
      </View>
    );
  }
  return (
    <View style={styles.risks}>
      <Txt size="xs" tone="subtle" weight="800" style={styles.kicker}>
        {strings.trends.topRisks.toUpperCase()}
      </Txt>
      {behaviors.map((b) => {
        const meta = behaviorMeta(b.behavior);
        const d = b.direction ? BEHAVIOR_DIRECTION_STYLE[b.direction] : null;
        return (
          <View key={b.behavior} style={styles.risk}>
            <View style={styles.riskIcon}>
              <Icon name={meta.icon} size={20} color={colors.foreground} />
            </View>
            <View style={styles.flex}>
              <Txt size="sm" weight="700">
                {meta.label}
              </Txt>
              <Txt size="xs" tone="muted">
                {strings.trends.inTrips(b.occurrences, b.trips)}
              </Txt>
            </View>
            {d && b.direction ? (
              <View style={styles.trendTag}>
                <Icon name={d.icon} size={14} color={d.color} />
                <Txt size="xs" weight="700" style={{ color: d.color }}>
                  {strings.trends.behaviorDirection[b.direction]}
                </Txt>
              </View>
            ) : null}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  kicker: { letterSpacing: 1.4 },
  tabular: { fontVariant: ['tabular-nums'] },
  chips: { flexDirection: 'row', gap: 6 },
  chip: {
    minHeight: 32,
    paddingHorizontal: 10,
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.input,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  headline: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  chart: { flexDirection: 'row', height: CHART_H, gap: 6 },
  axis: { width: 22 },
  axisLabel: { position: 'absolute', right: 0, fontSize: 10, lineHeight: 14 },
  plot: { flex: 1, flexDirection: 'row', alignItems: 'flex-end' },
  grid: { position: 'absolute', left: 0, right: 0, height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  column: { flex: 1, height: '100%', justifyContent: 'flex-end', alignItems: 'center', paddingHorizontal: 1 },
  bar: { width: '100%', maxWidth: 28, borderTopLeftRadius: 4, borderTopRightRadius: 4 },
  selected: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: radius.md,
    backgroundColor: colors.elevated,
    overflow: 'hidden',
  },
  dot: { width: 10, height: 10, borderRadius: 5 },
  stats: { flexDirection: 'row', gap: 8 },
  stat: {
    flex: 1,
    gap: 2,
    paddingVertical: 10,
    paddingHorizontal: 10,
    borderRadius: radius.md,
    backgroundColor: withAlpha(colors.foreground, 0.04),
  },
  risks: { gap: 10 },
  risk: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  riskIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    backgroundColor: colors.secondary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  trendTag: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  tip: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
});
