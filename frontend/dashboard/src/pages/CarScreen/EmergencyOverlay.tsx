import type { TripState } from '@/api/types'
import { Button } from '@/components/ui/button'
import { formatScore } from './carMeta'

interface EmergencyOverlayProps {
  /** The `emergency` event's data */
  trip: TripState
  soundOn: boolean
  onDismiss: () => void
}

/** Full-screen danger pulse (1 Hz) until dismissed. The siren loop is started and stopped by useCarScreen */
const EmergencyOverlay = ({ trip, soundOn, onDismiss }: EmergencyOverlayProps) => (
  <div role="alertdialog" aria-modal="true" aria-labelledby="emergency-title" className="fixed inset-0 z-50 grid place-items-center p-6">
    <div className="absolute inset-0 animate-alarm-pulse bg-danger" />
    <div className="relative flex max-w-xl flex-col items-center gap-6 rounded-lg border-2 border-danger bg-card p-10 text-center shadow-float">
      <span className="text-label text-muted-foreground uppercase">Score {formatScore(trip.score)}</span>
      <h2 id="emergency-title" className="text-display text-danger uppercase">
        Emergency
      </h2>
      <p className="text-h3">{trip.response.message}</p>
      <p className="text-body-sm text-muted-foreground">
        Driver {trip.driver_id}
        {!soundOn && ' · sound is off on this screen'}
      </p>
      <Button size="lg" className="h-12 bg-danger px-10 text-body font-semibold text-background hover:bg-danger/85" onClick={onDismiss} autoFocus>
        Dismiss
      </Button>
    </div>
  </div>
)

export default EmergencyOverlay
