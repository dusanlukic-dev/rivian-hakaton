import type { CarResponse, SoundLevel } from '@/api/types'
import { cn } from '@/lib/utils'
import Chip, { type ChipTone } from './Chip'

interface CarIndicatorsProps {
  response: CarResponse | null
  /** This screen's speaker is enabled */
  soundOn: boolean
}

const SOUND: Record<SoundLevel, { value: string; chip: string; tone: ChipTone | null }> = {
  none: { value: 'None', chip: 'Off', tone: null },
  low: { value: 'Low: chime', chip: 'Low', tone: 'caution' },
  high: { value: 'High: alarm', chip: 'High', tone: 'danger' },
}

const LIT: Record<ChipTone, string> = {
  neutral: '',
  safe: 'border-safe bg-safe-soft text-safe',
  caution: 'border-caution bg-caution-soft text-caution',
  danger: 'border-danger bg-danger-soft text-danger',
}

interface IndicatorProps {
  title: string
  value: string
  chip: string
  /** null = idle */
  tone: ChipTone | null
  note?: string
}

const Indicator = ({ title, value, chip, tone, note }: IndicatorProps) => (
  <div className={cn('flex items-center justify-between gap-4 rounded-md border bg-card p-5 transition-colors duration-300', tone && LIT[tone])}>
    <div className="flex min-w-0 flex-col gap-1">
      <span className={cn('text-label uppercase', !tone && 'text-muted-foreground')}>{title}</span>
      <span className={cn('text-h3', !tone && 'text-muted-foreground')}>{value}</span>
      {note && <span className="text-caption text-muted-foreground">{note}</span>}
    </div>
    <Chip tone={tone ?? 'neutral'} className={cn(tone && 'bg-card')}>
      {chip}
    </Chip>
  </div>
)

/** Seat vibration (`vibrate_seat`) and the current sound level (`sound`) */
const CarIndicators = ({ response, soundOn }: CarIndicatorsProps) => {
  const vibrating = response?.vibrate_seat ?? false
  const level = response?.sound ?? 'none'
  const sound = SOUND[level] ?? { value: level, chip: level, tone: 'danger' }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Indicator
        title="Seat vibration"
        value={vibrating ? 'Vibrating' : 'Off'}
        chip={vibrating ? 'On' : 'Off'}
        tone={vibrating ? (level === 'high' ? 'danger' : 'caution') : null}
      />
      <Indicator
        title="Sound"
        value={sound.value}
        chip={sound.chip}
        tone={sound.tone}
        note={level !== 'none' && !soundOn ? 'Muted on this screen' : undefined}
      />
    </div>
  )
}

export default CarIndicators
