import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export type ChipTone = 'neutral' | 'safe' | 'caution' | 'danger'

const TONES: Record<ChipTone, string> = {
  neutral: 'bg-muted text-muted-foreground',
  safe: 'bg-safe-soft text-safe',
  caution: 'bg-caution-soft text-caution',
  danger: 'bg-danger-soft text-danger',
}

/** Vigil chip: a state written as a word (label style) on its `-soft` background */
const Chip = ({ tone = 'neutral', className, children }: { tone?: ChipTone; className?: string; children: ReactNode }) => (
  <span className={cn('inline-flex h-6 shrink-0 items-center rounded-sm px-2 text-label whitespace-nowrap uppercase', TONES[tone], className)}>
    {children}
  </span>
)

export default Chip
