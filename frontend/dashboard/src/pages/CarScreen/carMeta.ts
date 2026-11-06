import type { Behavior, DashboardLight, SafetyLevel } from '@/api/types'

export interface BehaviorMeta {
  id: string
  label: string
}

/** The labels the backend knows (docs/API.md §4), in display order. Vigil: the word carries the meaning, no icons */
export const BEHAVIORS: (BehaviorMeta & { id: Behavior })[] = [
  { id: 'looking_at_phone', label: 'Looking at phone' },
  { id: 'eyes_off_road', label: 'Eyes off the road' },
  { id: 'looking_behind', label: 'Looking behind' },
  { id: 'turning_around', label: 'Turning around' },
  { id: 'hands_off_wheel', label: 'Hands off the wheel' },
  { id: 'drowsy', label: 'Drowsiness' },
]

/** Unknown labels (a newer backend) still render, with the raw label */
export const behaviorMeta = (id: string): BehaviorMeta => BEHAVIORS.find((b) => b.id === id) ?? { id, label: id }

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

/** Lamp colours are CSS variables in index.css: Vigil's safe / caution / danger (docs/API.md §7 names the four lights) */
const LIGHTS: Record<DashboardLight, { color: string; soft: string; name: string }> = {
  green: { color: 'var(--lamp-green)', soft: 'var(--lamp-green-soft)', name: 'Green' },
  green_yellow: { color: 'var(--lamp-green-yellow)', soft: 'var(--lamp-green-yellow-soft)', name: 'Green-yellow' },
  yellow: { color: 'var(--lamp-yellow)', soft: 'var(--lamp-yellow-soft)', name: 'Yellow' },
  red: { color: 'var(--lamp-red)', soft: 'var(--lamp-red-soft)', name: 'Red' },
}

const light = (value: string | undefined) => (value && Object.hasOwn(LIGHTS, value) ? LIGHTS[value as DashboardLight] : null)

/** State colour for a `dashboard_light` (text-safe on bg and surface) */
export const lightColor = (value: string | undefined) => light(value)?.color ?? 'var(--muted-foreground)'
/** Its `-soft` background, for alerts, chips and lit tiles */
export const lightSoftColor = (value: string | undefined) => light(value)?.soft ?? 'var(--muted)'
/** The light as a word, so the state is never colour-only */
export const lightName = (value: string | undefined) => light(value)?.name ?? value ?? 'Off'
/** State colour of a level, through its legend light */
export const levelColor = (level: string) => lightColor(LEVELS.find((l) => l.id === level)?.light)

/** 100 → "100", 87.25 → "87.3" */
export const formatScore = (score: number) => (Number.isInteger(score) ? String(score) : score.toFixed(1))

/** 436 → "7:16" */
export const formatDuration = (seconds: number) => {
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
