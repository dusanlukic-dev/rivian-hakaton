import type { DashboardLight, SafetyLevel } from '@/api/types';

/** Blackish-gray neutral palette, same tokens as the web dashboard's dark theme (Tailwind neutral). */
export const colors = {
  background: '#0a0a0a',
  card: '#171717',
  elevated: '#1f1f1f',
  secondary: '#262626',
  border: 'rgba(255,255,255,0.10)',
  input: 'rgba(255,255,255,0.15)',
  foreground: '#fafafa',
  muted: '#a1a1a1',
  subtle: '#737373',
  primary: '#e5e5e5',
  primaryForeground: '#171717',
  destructive: '#ff6467',
  alarm: '#EF4444',
  alarmDeep: '#7f1d1d',
  ok: '#22C55E',
  warn: '#FACC15',
} as const;

/** docs/API.md §7 suggested lamp colours. */
export const lampColors: Record<DashboardLight, string> = {
  green: '#22C55E',
  green_yellow: '#A3E635',
  yellow: '#FACC15',
  red: '#EF4444',
};

export const LEVELS: SafetyLevel[] = ['safe', 'caution', 'warning', 'high_risk', 'critical', 'emergency'];

export const levelColors: Record<SafetyLevel, string> = {
  safe: '#22C55E',
  caution: '#A3E635',
  warning: '#FACC15',
  high_risk: '#F97316',
  critical: '#EF4444',
  emergency: '#DC2626',
};

export const radius = { sm: 8, md: 12, lg: 16, xl: 24, full: 999 } as const;

/** "#RRGGBB" + alpha 0..1 → "#RRGGBBAA" */
export const withAlpha = (hex: string, alpha: number) =>
  `${hex}${Math.round(Math.min(1, Math.max(0, alpha)) * 255)
    .toString(16)
    .padStart(2, '0')}`;
