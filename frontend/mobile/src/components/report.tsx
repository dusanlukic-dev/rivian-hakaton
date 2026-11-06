import { Image } from 'expo-image';
import { Fragment, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, View, type LayoutChangeEvent } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Defs, Line, LinearGradient, Path, Rect, Stop, Text as SvgText } from 'react-native-svg';

import type { DangerLevel, DangerMoment, TripSection } from '@/api/types';
import { behaviorMeta } from '@/config/behaviors';
import { strings } from '@/config/strings';
import { formatDuration, formatScore } from '@/lib/format';
import { colors, levelColors, radius, withAlpha } from '@/theme/colors';

import { Button, Card, Icon, Pill, Txt } from './ui';

/** The backend decides the danger (docs/API.md §4 DangerLevel); these are only its colours. */
export const dangerColors: Record<DangerLevel, string> = {
  none: colors.subtle,
  dangerous: '#F59E0B',
  critical: '#EF4444',
};

const PLOT_H = 170;
const LEFT = 30;
const RIGHT = 10;
const BOTTOM = 24;
const BOX_W = 76;
const BOX_H = 56;
const ROWS = 2;
const ROW_GAP = 8;
const BOX_TOP_SPACE = ROWS * BOX_H + (ROWS - 1) * ROW_GAP + 16;

interface ImageBox {
  moment: DangerMoment;
  left: number;
  top: number;
  center: number;
}

/**
 * The drive: score over time (each 2 s section's end score), dangerous sections shaded, a node per dangerous
 * moment, and for the critical ("ultra dangerous") ones a small box with the picture of that moment above the
 * node. Everything comes from GET /trips/{id}/report; the app only draws it.
 */
export function DriveChart({
  sections,
  moments,
  onSelect,
}: {
  sections: TripSection[];
  moments: DangerMoment[];
  onSelect: (moment: DangerMoment) => void;
}) {
  const [width, setWidth] = useState(0);
  const withImages = moments.filter((m) => m.danger === 'critical' && m.image_url);
  const top = withImages.length ? BOX_TOP_SPACE : 12;
  const height = top + PLOT_H + BOTTOM;
  const tMax = Math.max(sections.at(-1)?.t_end ?? 0, ...moments.map((m) => m.t_end), 1);
  const plotW = Math.max(width - LEFT - RIGHT, 1);
  const x = (t: number) => LEFT + (Math.min(Math.max(t, 0), tMax) / tMax) * plotW;
  const y = (score: number) => top + (1 - Math.min(Math.max(score, 0), 100) / 100) * PLOT_H;

  const points: [number, number][] = [
    [0, sections[0]?.score_start ?? 100],
    ...sections.map((s): [number, number] => [s.t_end, s.score_end]),
  ];
  const line = points.map(([t, score], i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(score).toFixed(1)}`).join(' ');
  const lastT = points[points.length - 1][0];
  const area = `${line} L${x(lastT).toFixed(1)},${y(0)} L${x(0)},${y(0)} Z`;

  // Greedy layout of the picture boxes: nearest row first, skip a box if both rows are taken there.
  const boxes: ImageBox[] = [];
  const rowEnds = Array<number>(ROWS).fill(-Infinity);
  for (const moment of [...withImages].sort((a, b) => a.peak_t - b.peak_t)) {
    const center = Math.min(Math.max(x(moment.peak_t), LEFT + BOX_W / 2), width - RIGHT - BOX_W / 2);
    const left = center - BOX_W / 2;
    const row = rowEnds.findIndex((end) => left >= end + 6);
    if (row === -1) continue;
    rowEnds[row] = left + BOX_W;
    boxes.push({ moment, left, top: top - 12 - BOX_H - row * (BOX_H + ROW_GAP), center });
  }

  return (
    <View onLayout={(e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)} style={{ height }}>
      {width > 0 ? (
        <>
          <Svg width={width} height={height}>
            <Defs>
              <LinearGradient id="score" x1="0" y1={y(100)} x2="0" y2={y(0)} gradientUnits="userSpaceOnUse">
                <Stop offset="0" stopColor={levelColors.safe} stopOpacity={0.35} />
                <Stop offset="0.45" stopColor={levelColors.warning} stopOpacity={0.22} />
                <Stop offset="1" stopColor={levelColors.critical} stopOpacity={0.3} />
              </LinearGradient>
            </Defs>
            {sections
              .filter((s) => s.danger !== 'none')
              .map((s) => (
                <Rect
                  key={s.section_id}
                  x={x(s.t_start)}
                  y={top}
                  width={Math.max(x(s.t_end) - x(s.t_start), 1.5)}
                  height={PLOT_H}
                  fill={dangerColors[s.danger]}
                  opacity={s.danger === 'critical' ? 0.24 : 0.14}
                />
              ))}
            {[100, 75, 50, 25, 0].map((v) => (
              <Fragment key={v}>
                <Line x1={LEFT} x2={width - RIGHT} y1={y(v)} y2={y(v)} stroke={colors.border} strokeWidth={1} />
                <SvgText x={LEFT - 6} y={y(v) + 3.5} fontSize={10} fill={colors.subtle} textAnchor="end">
                  {v}
                </SvgText>
              </Fragment>
            ))}
            <Path d={area} fill="url(#score)" />
            <Path d={line} stroke={colors.foreground} strokeWidth={2} fill="none" strokeLinejoin="round" />
            {boxes.map((b) => (
              <Line
                key={`c${b.moment.moment_id}`}
                x1={b.center}
                y1={b.top + BOX_H}
                x2={x(b.moment.peak_t)}
                y2={y(b.moment.peak_score)}
                stroke={dangerColors.critical}
                strokeWidth={1.5}
                strokeDasharray="3 3"
              />
            ))}
            {moments.map((m) => (
              <Circle
                key={m.moment_id}
                cx={x(m.peak_t)}
                cy={y(m.peak_score)}
                r={m.danger === 'critical' ? 6.5 : 4.5}
                fill={dangerColors[m.danger]}
                stroke={colors.background}
                strokeWidth={2}
              />
            ))}
            <SvgText x={LEFT} y={top + PLOT_H + 16} fontSize={10} fill={colors.subtle}>
              0:00
            </SvgText>
            <SvgText x={width - RIGHT} y={top + PLOT_H + 16} fontSize={10} fill={colors.subtle} textAnchor="end">
              {formatDuration(tMax)}
            </SvgText>
          </Svg>
          {moments.map((m) => (
            <Pressable
              key={`hit${m.moment_id}`}
              accessibilityRole="button"
              accessibilityLabel={strings.report.momentAt(formatDuration(m.peak_t))}
              onPress={() => onSelect(m)}
              style={[styles.hit, { left: x(m.peak_t) - 16, top: y(m.peak_score) - 16 }]}
            />
          ))}
          {boxes.map((b) => (
            <Pressable
              key={`box${b.moment.moment_id}`}
              accessibilityRole="imagebutton"
              accessibilityLabel={strings.report.momentAt(formatDuration(b.moment.peak_t))}
              onPress={() => onSelect(b.moment)}
              style={[styles.box, { left: b.left, top: b.top }]}
            >
              <Image source={{ uri: b.moment.image_url ?? undefined }} style={styles.fill} contentFit="cover" transition={150} />
            </Pressable>
          ))}
        </>
      ) : null}
    </View>
  );
}

export function ChartLegend() {
  return (
    <View style={styles.legend}>
      <LegendItem color={dangerColors.dangerous} label={strings.report.dangerous} />
      <LegendItem color={dangerColors.critical} label={strings.report.critical} />
      <View style={styles.legendItem}>
        <View style={[styles.legendLine]} />
        <Txt size="xs" tone="muted">
          {strings.report.score}
        </Txt>
      </View>
    </View>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendSwatch, { backgroundColor: withAlpha(color, 0.6) }]} />
      <Txt size="xs" tone="muted">
        {label}
      </Txt>
    </View>
  );
}

function behaviorsText(behaviors: DangerMoment['behaviors']) {
  return Object.entries(behaviors)
    .map(([key, seconds]) => `${behaviorMeta(key).label} ${(seconds ?? 0).toFixed(1)} s`)
    .join(' · ');
}

/** Dangerous moments, worst (biggest score drop) first. */
export function MomentList({ moments, onSelect }: { moments: DangerMoment[]; onSelect: (m: DangerMoment) => void }) {
  const ordered = [...moments].sort((a, b) => b.score_drop - a.score_drop || b.t_start - a.t_start);
  return (
    <View style={styles.list}>
      {ordered.map((m) => (
        <Pressable key={m.moment_id} onPress={() => onSelect(m)} accessibilityRole="button">
          <Card style={styles.momentCard}>
            {m.image_url ? (
              <Image source={{ uri: m.image_url }} style={styles.thumb} contentFit="cover" transition={150} />
            ) : (
              <View style={[styles.thumb, styles.noThumb]}>
                <Icon name="image-off-outline" size={22} color={colors.subtle} />
              </View>
            )}
            <View style={styles.flex}>
              <View style={styles.row}>
                <Pill label={strings.report.dangerLabel[m.danger]} color={dangerColors[m.danger]} />
                <Txt size="xs" tone="subtle">
                  {strings.report.momentAt(formatDuration(m.t_start))} · {formatDuration(m.duration_s)}
                </Txt>
              </View>
              <Txt size="sm" weight="700" numberOfLines={2}>
                {behaviorsText(m.behaviors) || strings.report.modelAlarm}
              </Txt>
              <Txt size="xs" tone="muted">
                {strings.report.cost(m.score_drop)} · {Math.round(m.speed_avg_kmh)} km/h
              </Txt>
            </View>
          </Card>
        </Pressable>
      ))}
    </View>
  );
}

/** Everything about one moment: the picture, what was detected, what it cost. */
export function MomentSheet({ moment, onClose }: { moment: DangerMoment | null; onClose: () => void }) {
  const insets = useSafeAreaInsets(); // keep Close above Android's navigation bar
  return (
    <Modal visible={moment !== null} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} accessibilityLabel={strings.report.close} />
      {moment ? (
        <View style={styles.sheet}>
          <ScrollView contentContainerStyle={[styles.sheetContent, { paddingBottom: insets.bottom + 20 }]}>
            {moment.image_url ? (
              <Image source={{ uri: moment.image_url }} style={styles.photo} contentFit="contain" transition={150} />
            ) : null}
            <View style={styles.row}>
              <Pill label={strings.report.dangerLabel[moment.danger]} color={dangerColors[moment.danger]} />
              <Txt size="sm" tone="muted">
                {formatDuration(moment.t_start)}–{formatDuration(moment.t_end)} · {formatDuration(moment.duration_s)}
              </Txt>
            </View>
            <Txt size="lg" weight="800">
              {strings.report.cost(moment.score_drop)}
            </Txt>
            <Txt size="sm" tone="muted">
              {strings.report.scoreRange(formatScore(moment.score_start), formatScore(moment.score_min))} ·{' '}
              {strings.levels[moment.level]} · {Math.round(moment.speed_avg_kmh)}–{Math.round(moment.speed_max_kmh)} km/h
            </Txt>
            <Txt size="xs" tone="subtle" weight="800" style={styles.kicker}>
              {strings.report.seen.toUpperCase()}
            </Txt>
            {Object.entries(moment.behaviors).length ? (
              Object.entries(moment.behaviors).map(([key, seconds]) => {
                const meta = behaviorMeta(key);
                return (
                  <View key={key} style={styles.row}>
                    <Icon name={meta.icon} size={20} color={dangerColors[moment.danger]} />
                    <Txt style={styles.flex}>{meta.label}</Txt>
                    <Txt weight="700">{(seconds ?? 0).toFixed(1)} s</Txt>
                  </View>
                );
              })
            ) : (
              <Txt size="sm">{strings.report.modelAlarm}</Txt>
            )}
            {Object.keys(moment.categories).length ? (
              <>
                <Txt size="xs" tone="subtle" weight="800" style={styles.kicker}>
                  {strings.report.model.toUpperCase()}
                </Txt>
                {Object.entries(moment.categories).map(([name, p]) => (
                  <View key={name} style={styles.row}>
                    <Txt size="sm" style={styles.flex}>
                      {name.replace(/_/g, ' ')}
                    </Txt>
                    <View style={styles.barTrack}>
                      <View style={[styles.barFill, { width: `${Math.round(p * 100)}%`, backgroundColor: dangerColors[moment.danger] }]} />
                    </View>
                    <Txt size="sm" weight="700" style={styles.pct}>
                      {Math.round(p * 100)}%
                    </Txt>
                  </View>
                ))}
                {moment.rules_triggered.length ? (
                  <Txt size="xs" tone="muted">
                    {strings.report.rules}: {moment.rules_triggered.map((r) => r.replace(/_/g, ' ')).join(', ')}
                    {moment.peak_risk !== null ? ` · ${strings.report.risk} ${Math.round(moment.peak_risk * 100)}%` : ''}
                  </Txt>
                ) : null}
              </>
            ) : null}
            <Button label={strings.report.close} variant="secondary" onPress={onClose} />
          </ScrollView>
        </View>
      ) : null}
    </Modal>
  );
}

/** Slots on the Drive screen strip: 30 × 2 s = the last minute. Newest on the right, like a scrolling timeline. */
const RECENT_SLOTS = 30;

/** Drive screen: the last minute, one bar per 2 s section (height = score, colour = danger). */
export function RecentSections({ sections }: { sections: TripSection[] }) {
  if (sections.length === 0) return null;
  const shown = sections.slice(-RECENT_SLOTS);
  const empty = RECENT_SLOTS - shown.length;
  const last = sections[sections.length - 1];
  const seen = behaviorsText(last.behaviors);
  return (
    <Card style={styles.recent}>
      <View style={styles.row}>
        <Txt size="xs" tone="subtle" weight="800" style={[styles.kicker, styles.flex]}>
          {strings.report.lastMinute.toUpperCase()}
        </Txt>
        {last.risk_max !== null ? (
          <Txt size="xs" tone="muted">
            {strings.report.risk} {Math.round(last.risk_max * 100)}%
          </Txt>
        ) : null}
      </View>
      <View style={styles.bars}>
        {Array.from({ length: empty }, (_, i) => (
          <View key={`empty${i}`} style={[styles.bar, styles.emptyBar]} />
        ))}
        {shown.map((s) => (
          <View
            key={s.section_id}
            style={[
              styles.bar,
              {
                height: 6 + (Math.max(s.score_end, 0) / 100) * 38,
                backgroundColor: s.danger === 'none' ? withAlpha(levelColors[s.level], 0.45) : dangerColors[s.danger],
              },
            ]}
          />
        ))}
      </View>
      <Txt size="xs" tone={seen ? 'default' : 'muted'} numberOfLines={2}>
        {seen ? `${strings.report.lastSection}: ${seen}` : strings.report.lastSectionClean}
      </Txt>
    </Card>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  fill: { width: '100%', height: '100%' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  kicker: { letterSpacing: 1.2 },
  hit: { position: 'absolute', width: 32, height: 32, borderRadius: 16 },
  box: {
    position: 'absolute',
    width: BOX_W,
    height: BOX_H,
    borderRadius: radius.sm,
    borderWidth: 2,
    borderColor: dangerColors.critical,
    overflow: 'hidden',
    backgroundColor: colors.elevated,
  },
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendSwatch: { width: 12, height: 12, borderRadius: 3 },
  legendLine: { width: 14, height: 2, backgroundColor: colors.foreground, borderRadius: 1 },
  list: { gap: 10 },
  momentCard: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 10 },
  thumb: { width: 84, height: 63, borderRadius: radius.sm, backgroundColor: colors.elevated },
  noThumb: { alignItems: 'center', justifyContent: 'center' },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)' },
  sheet: {
    maxHeight: '85%',
    backgroundColor: colors.card,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    borderColor: colors.border,
    borderWidth: 1,
  },
  sheetContent: { padding: 20, gap: 10 },
  photo: { width: '100%', aspectRatio: 4 / 3, borderRadius: radius.md, backgroundColor: colors.elevated },
  barTrack: { width: 90, height: 6, borderRadius: 3, backgroundColor: colors.secondary, overflow: 'hidden' },
  barFill: { height: 6, borderRadius: 3 },
  pct: { width: 40, textAlign: 'right' },
  recent: { gap: 8 },
  bars: { flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 44 },
  bar: { flex: 1, borderRadius: 2 },
  emptyBar: { height: 6, backgroundColor: colors.secondary },
});
