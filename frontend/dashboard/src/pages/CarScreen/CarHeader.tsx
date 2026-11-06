import { HugeiconsIcon } from '@hugeicons/react'
import { SecurityCheckIcon, VolumeHighIcon, VolumeMute02Icon, VolumeOffIcon } from '@hugeicons/core-free-icons'
import type { TripState } from '@/api/types'
import type { LiveStatus } from '@/hooks/useLive'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface SoundControl {
  on: boolean
  /** On, but the browser still wants a gesture on this page load */
  blocked: boolean
  toggle: () => void
}

interface CarHeaderProps {
  status: LiveStatus
  trip: TripState | null
  sound: SoundControl
}

const STATUS: Record<LiveStatus, { label: string; dot: string }> = {
  open: { label: 'Live', dot: 'bg-lamp-green' },
  connecting: { label: 'Connecting…', dot: 'bg-lamp-yellow animate-pulse' },
  reconnecting: { label: 'Reconnecting…', dot: 'bg-lamp-red animate-pulse' },
  idle: { label: 'Offline', dot: 'bg-muted-foreground' },
}

const CarHeader = ({ status, trip, sound }: CarHeaderProps) => {
  const { label, dot } = STATUS[status]
  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b px-4 py-3 lg:px-6">
      <div className="flex items-center gap-3">
        <div className="grid size-10 place-items-center rounded-lg bg-primary text-primary-foreground">
          <HugeiconsIcon icon={SecurityCheckIcon} size={22} />
        </div>
        <div>
          <h1 className="text-lg leading-tight font-bold">{__BRAND__.name}</h1>
          {__BRAND__.tagline && <p className="text-xs text-muted-foreground">{__BRAND__.tagline}</p>}
        </div>
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-3 text-sm">
        {trip ? (
          <span className="text-muted-foreground">
            Trip <code className="font-mono text-foreground" title={trip.trip_id}>{trip.trip_id.slice(0, 8)}</code>
            {' · '}Driver <span className="text-foreground">{trip.driver_id}</span>
          </span>
        ) : (
          <span className="text-muted-foreground">No active trip</span>
        )}

        <span className="flex items-center gap-2 rounded-full bg-muted px-3 py-1" role="status">
          <span className={cn('size-2 rounded-full', dot)} />
          {label}
        </span>

        <Button
          size="lg"
          variant={sound.on && !sound.blocked ? 'outline' : 'default'}
          onClick={sound.toggle}
          title={sound.on && !sound.blocked ? 'Mute this screen' : undefined}
        >
          <HugeiconsIcon icon={!sound.on ? VolumeOffIcon : sound.blocked ? VolumeMute02Icon : VolumeHighIcon} />
          {!sound.on ? 'Enable sound' : sound.blocked ? 'Click to unlock sound' : 'Sound on'}
        </Button>
      </div>
    </header>
  )
}

export default CarHeader
