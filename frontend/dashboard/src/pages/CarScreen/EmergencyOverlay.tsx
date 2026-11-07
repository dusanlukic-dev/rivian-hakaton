import { HugeiconsIcon } from '@hugeicons/react'
import { SirenIcon } from '@hugeicons/core-free-icons'
import type { TripState } from '@/api/types'
import { Button } from '@/components/ui/button'
import { formatScore, isCollapse } from './carMeta'

interface EmergencyOverlayProps {
  /** The `emergency` event's data */
  trip: TripState
  soundOn: boolean
  onDismiss: () => void
}

/** Full-screen red pulse (1 Hz) until dismissed. The siren loop is started and stopped by useCarScreen */
const EmergencyOverlay = ({ trip, soundOn, onDismiss }: EmergencyOverlayProps) => (
  <div role="alertdialog" aria-modal="true" aria-labelledby="emergency-title" className="fixed inset-0 z-50 grid place-items-center p-6">
    <div className="absolute inset-0 animate-alarm-pulse bg-lamp-red" />
    <div className="relative flex max-w-xl flex-col items-center gap-5 rounded-2xl bg-background/90 p-10 text-center shadow-2xl ring-2 ring-lamp-red">
      <HugeiconsIcon icon={SirenIcon} size={64} className="text-lamp-red" />
      <h2 id="emergency-title" className="text-4xl font-black tracking-wider text-lamp-red uppercase">
        Emergency
      </h2>
      {isCollapse(trip) && <p className="text-2xl font-bold">The driver is not responding</p>}
      <p className="text-xl">{trip.response.message}</p>
      <p className="text-sm text-muted-foreground">
        Score {formatScore(trip.score)} · Driver {trip.driver_id}
        {!soundOn && ' · sound is off on this screen'}
      </p>
      <Button size="lg" className="bg-lamp-red px-10 py-6 text-base font-semibold text-background hover:bg-lamp-red/85" onClick={onDismiss} autoFocus>
        Dismiss
      </Button>
    </div>
  </div>
)

export default EmergencyOverlay
