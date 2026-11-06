import {
  Alert02Icon,
  Rotate360Icon,
  SleepingIcon,
  SmartPhone01Icon,
  SteeringIcon,
  ViewIcon,
  ViewOffSlashIcon,
} from '@hugeicons/core-free-icons'
import type { IconSvgElement } from '@hugeicons/react'
import type { Behavior, DashboardLight, SafetyLevel } from '@/api/types'

export interface BehaviorMeta {
  id: string
  label: string
  icon: IconSvgElement
}

/** The labels the backend knows (docs/API.md §4), in display order */
export const BEHAVIORS: (BehaviorMeta & { id: Behavior })[] = [
  { id: 'looking_at_phone', label: 'Looking at phone', icon: SmartPhone01Icon },
  { id: 'eyes_off_road', label: 'Eyes off the road', icon: ViewOffSlashIcon },
  { id: 'looking_behind', label: 'Looking behind', icon: ViewIcon },
  { id: 'turning_around', label: 'Turning around', icon: Rotate360Icon },
  { id: 'hands_off_wheel', label: 'Hands off the wheel', icon: SteeringIcon },
  { id: 'drowsy', label: 'Drowsiness', icon: SleepingIcon },
]

/** Unknown labels (a newer backend) still render: generic icon + the raw label */
export const behaviorMeta = (id: string): BehaviorMeta =>
  BEHAVIORS.find((b) => b.id === id) ?? { id, label: id, icon: Alert02Icon }

/** Display legend only: the level always comes from the backend, never computed here */
export const LEVELS: { id: SafetyLevel; label: string; light: DashboardLight }[] = [
  { id: 'safe', label: 'Safe', light: 'green' },
  { id: 'caution', label: 'Caution', light: 'green_yellow' },
  { id: 'warning', label: 'Warning', light: 'yellow' },
  { id: 'high_risk', label: 'High risk', light: 'yellow' },
  { id: 'critical', label: 'Critical', light: 'red' },
  { id: 'emergency', label: 'Emergency', light: 'red' },
]

export const levelLabel = (level: string) => LEVELS.find((l) => l.id === level)?.label ?? level

/** Lamp colours are CSS variables in index.css (values from docs/API.md §7) */
const LIGHT_VARS: Record<DashboardLight, string> = {
  green: 'var(--lamp-green)',
  green_yellow: 'var(--lamp-green-yellow)',
  yellow: 'var(--lamp-yellow)',
  red: 'var(--lamp-red)',
}

export const lightColor = (light: string | undefined) =>
  (light && LIGHT_VARS[light as DashboardLight]) || 'var(--muted-foreground)'

/** 100 → "100", 87.25 → "87.3" */
export const formatScore = (score: number) => (Number.isInteger(score) ? String(score) : score.toFixed(1))

/** 436 → "7:16" */
export const formatDuration = (seconds: number) => {
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
