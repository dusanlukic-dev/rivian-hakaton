import { StyleSheet, View } from 'react-native';

import type { Behavior, CarResponse, DashboardLight, SafetyLevel } from '@/api/types';
import { BEHAVIORS, behaviorMeta } from '@/config/behaviors';
import { strings } from '@/config/strings';
import { formatScore } from '@/lib/format';
import { useLive } from '@/state/live';
import { colors, lampColors, LEVELS, levelColors, radius, withAlpha } from '@/theme/colors';

import { Icon, Pill, Txt, type IconName } from './ui';

/** Big dashboard lamp: colour = response.dashboard_light, score inside. */
export function Lamp({ light, score, level }: { light: DashboardLight; score: number; level: SafetyLevel }) {
  const c = lampColors[light];
  return (
    <View
      style={[
        styles.lamp,
        { borderColor: c, backgroundColor: withAlpha(c, 0.1), boxShadow: `0 0 56px 4px ${withAlpha(c, 0.45)}` },
      ]}>
      <Txt size="display" weight="900" style={styles.tabular}>
        {formatScore(score)}
      </Txt>
      <Txt size="sm" tone="muted">
        {strings.drive.score}
      </Txt>
      <View style={[styles.levelChip, { backgroundColor: c }]}>
        <Txt size="sm" weight="900" tone="inverse">
          {strings.levels[level].toUpperCase()}
        </Txt>
      </View>
    </View>
  );
}

/** safe → emergency, current level highlighted. */
export function LevelBar({ level }: { level: SafetyLevel }) {
  const current = LEVELS.indexOf(level);
  return (
    <View style={styles.levelBar}>
      {LEVELS.map((l, i) => (
        <View
          key={l}
          style={[styles.segment, { backgroundColor: levelColors[l], opacity: i === current ? 1 : 0.2, flex: i === current ? 2.2 : 1 }]}
        />
      ))}
    </View>
  );
}

/** One tile per known behaviour (+ unknown labels from the backend). Lit while active, with seconds. */
export function BehaviorGrid({ active }: { active: Partial<Record<Behavior, number>> }) {
  const activeMap = active as Record<string, number | undefined>;
  const extra = Object.keys(activeMap)
    .filter((key) => !BEHAVIORS.some((b) => b.key === key))
    .map(behaviorMeta);
  return (
    <View style={styles.grid}>
      {[...BEHAVIORS, ...extra].map((b) => {
        const seconds = activeMap[b.key];
        const on = seconds !== undefined;
        return (
          <View
            key={b.key}
            style={[styles.tile, on && { borderColor: colors.alarm, backgroundColor: withAlpha(colors.alarm, 0.16) }]}>
            <Icon name={b.icon} size={28} color={on ? colors.alarm : colors.subtle} />
            <Txt size="xs" weight="600" tone={on ? 'default' : 'subtle'} numberOfLines={2} style={styles.center}>
              {b.label}
            </Txt>
            <Txt size="xs" weight="800" style={{ color: on ? colors.alarm : 'transparent' }}>
              {on ? `${seconds.toFixed(0)} s` : '–'}
            </Txt>
          </View>
        );
      })}
    </View>
  );
}

function Indicator({ icon, label, value, color }: { icon: IconName; label: string; value: string; color: string }) {
  return (
    <View style={styles.indicator}>
      <Icon name={icon} size={22} color={color} />
      <Txt size="xs" tone="subtle" weight="600">
        {label}
      </Txt>
      <Txt size="sm" weight="700" style={{ color }}>
        {value}
      </Txt>
    </View>
  );
}

/** What the car does right now: seat vibration, sound, camera data freshness. */
export function Indicators({ response, stale }: { response: CarResponse; stale: boolean }) {
  const soundIcon: IconName = response.sound === 'high' ? 'volume-high' : response.sound === 'low' ? 'volume-low' : 'volume-off';
  return (
    <View style={styles.indicators}>
      <Indicator
        icon="car-seat"
        label={strings.drive.seatVibration}
        value={response.vibrate_seat ? strings.drive.vibrating : strings.drive.still}
        color={response.vibrate_seat ? colors.alarm : colors.muted}
      />
      <Indicator
        icon={soundIcon}
        label={strings.drive.sound}
        value={strings.sound[response.sound]}
        color={response.sound === 'high' ? colors.alarm : response.sound === 'low' ? colors.warn : colors.muted}
      />
      <Indicator
        icon={stale ? 'wifi-off' : 'wifi'}
        label={strings.drive.data}
        value={stale ? strings.drive.stale : strings.drive.live}
        color={stale ? colors.warn : colors.ok}
      />
    </View>
  );
}

/** Connection to the car computer. Steady while the socket retries (see `LinkState`). */
export function StatusPill() {
  const link = useLive((s) => s.link);
  const color = link === 'online' ? colors.ok : link === 'checking' ? colors.subtle : colors.warn;
  return <Pill label={strings.link[link]} color={color} />;
}

/** Round score badge for lists and summaries. */
export function ScoreBadge({ score, level, size = 52 }: { score: number; level: SafetyLevel; size?: number }) {
  const c = levelColors[level];
  return (
    <View
      style={[
        styles.badge,
        { width: size, height: size, borderRadius: size / 2, borderColor: c, backgroundColor: withAlpha(c, 0.12) },
      ]}>
      <Txt weight="900" style={[styles.tabular, { color: c, fontSize: size * 0.32, lineHeight: size * 0.4 }]}>
        {Math.round(score)}
      </Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  tabular: { fontVariant: ['tabular-nums'] },
  center: { textAlign: 'center' },
  lamp: {
    width: 248,
    height: 248,
    borderRadius: 124,
    borderWidth: 6,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  levelChip: { marginTop: 8, borderRadius: radius.full, paddingHorizontal: 12, paddingVertical: 3 },
  levelBar: { flexDirection: 'row', gap: 4, height: 10 },
  segment: { borderRadius: 5 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tile: {
    width: '31.6%',
    minHeight: 104,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    padding: 8,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  indicators: { flexDirection: 'row', gap: 8 },
  indicator: {
    flex: 1,
    alignItems: 'center',
    gap: 2,
    paddingVertical: 10,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  badge: { borderWidth: 3, alignItems: 'center', justifyContent: 'center' },
});
