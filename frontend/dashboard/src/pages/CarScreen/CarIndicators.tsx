import type { ReactNode } from 'react'
import { HugeiconsIcon, type IconSvgElement } from '@hugeicons/react'
import { SeatSelectorIcon, VolumeHighIcon, VolumeLowIcon, VolumeOffIcon } from '@hugeicons/core-free-icons'
import type { CarResponse, SoundLevel } from '@/api/types'
import { cn } from '@/lib/utils'

interface CarIndicatorsProps {
  response: CarResponse | null
  /** This screen's speaker is enabled */
  soundOn: boolean
}

const SOUND: Record<SoundLevel, { value: string; icon: IconSvgElement }> = {
  none: { value: 'None', icon: VolumeOffIcon },
  low: { value: 'Low: chime', icon: VolumeLowIcon },
  high: { value: 'High: alarm', icon: VolumeHighIcon },
}

const Indicator = ({ icon, title, value, active, children }: { icon: ReactNode; title: string; value: string; active: boolean; children?: ReactNode }) => (
  <div className={cn('flex items-center gap-4 rounded-lg bg-card p-4 ring-1', active ? 'ring-lamp-yellow' : 'ring-foreground/10')}>
    {icon}
    <div className="flex min-w-0 flex-col">
      <span className="text-xs tracking-widest text-muted-foreground uppercase">{title}</span>
      <span className={cn('text-lg font-semibold', !active && 'text-muted-foreground')}>{value}</span>
      {children}
    </div>
  </div>
)

/** Seat vibration (`vibrate_seat`) and the current sound level (`sound`) */
const CarIndicators = ({ response, soundOn }: CarIndicatorsProps) => {
  const vibrating = response?.vibrate_seat ?? false
  const level = response?.sound ?? 'none'
  const sound = SOUND[level] ?? { value: level, icon: VolumeHighIcon }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Indicator
        title="Seat vibration"
        value={vibrating ? 'Vibrating' : 'Off'}
        active={vibrating}
        icon={
          <div className="relative grid size-14 shrink-0 place-items-center rounded-full bg-muted">
            {/* animate-ping: 1 cycle per second */}
            {vibrating && <span className="absolute inset-0 animate-ping rounded-full bg-lamp-yellow/50" />}
            <HugeiconsIcon icon={SeatSelectorIcon} size={28} className={cn('relative', vibrating && 'text-lamp-yellow')} />
          </div>
        }
      />
      <Indicator
        title="Sound"
        value={sound.value}
        active={level !== 'none'}
        icon={
          <div className="grid size-14 shrink-0 place-items-center rounded-full bg-muted">
            <HugeiconsIcon icon={sound.icon} size={28} className={cn(level === 'high' ? 'text-lamp-red' : level === 'low' && 'text-lamp-yellow')} />
          </div>
        }
      >
        {level !== 'none' && !soundOn && <span className="text-xs text-muted-foreground">Muted on this screen</span>}
      </Indicator>
    </div>
  )
}

export default CarIndicators
