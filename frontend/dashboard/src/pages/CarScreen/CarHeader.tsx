import { useTheme } from 'next-themes'
import type { TripState } from '@/api/types'
import type { LiveStatus } from '@/hooks/useLive'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { lightColor } from './carMeta'
import Wordmark from './Wordmark'

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
  open: { label: 'Live', dot: 'bg-safe' },
  connecting: { label: 'Connecting', dot: 'bg-caution' },
  reconnecting: { label: 'Reconnecting', dot: 'bg-danger' },
  idle: { label: 'Offline', dot: 'bg-muted-foreground' },
}

/** Day / night: Vigil's light and dark themes (next-themes keeps the choice) */
const ThemeSwitch = () => {
  const { resolvedTheme, setTheme } = useTheme()
  const options = [
    { id: 'light', label: 'Day' },
    { id: 'dark', label: 'Night' },
  ]
  return (
    <div role="group" aria-label="Theme" className="flex h-12 items-center gap-1 rounded-md border p-1">
      {options.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          aria-pressed={resolvedTheme === id}
          onClick={() => setTheme(id)}
          className={cn(
            'h-full rounded-sm px-3 text-label uppercase transition-colors duration-300',
            resolvedTheme === id ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

const CarHeader = ({ status, trip, sound }: CarHeaderProps) => {
  const { label, dot } = STATUS[status]
  return (
    <header className="flex flex-wrap items-center gap-x-8 gap-y-4 border-b px-4 py-4 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-1.5">
        <Wordmark name={__BRAND__.name} lens={trip ? lightColor(trip.response.dashboard_light) : undefined} className="text-h2 leading-none" />
        {__BRAND__.tagline && <p className="text-caption text-muted-foreground">{__BRAND__.tagline}</p>}
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-x-6 gap-y-3">
        {trip ? (
          <dl className="flex items-baseline gap-5 text-body-sm">
            <div className="flex items-baseline gap-2">
              <dt className="text-label text-muted-foreground uppercase">Trip</dt>
              <dd title={trip.trip_id}>{trip.trip_id.slice(0, 8)}</dd>
            </div>
            <div className="flex items-baseline gap-2">
              <dt className="text-label text-muted-foreground uppercase">Driver</dt>
              <dd>{trip.driver_id}</dd>
            </div>
          </dl>
        ) : (
          <span className="text-body-sm text-muted-foreground">No active trip</span>
        )}

        <span className="flex h-8 items-center gap-2 rounded-full border px-3 text-label uppercase" role="status">
          <span className={cn('size-2 rounded-full', dot)} />
          {label}
        </span>

        <ThemeSwitch />

        <Button
          size="lg"
          variant={sound.on && !sound.blocked ? 'outline' : 'default'}
          onClick={sound.toggle}
          title={sound.on && !sound.blocked ? 'Mute this screen' : undefined}
          className="h-12 px-5 text-body-sm"
        >
          {!sound.on ? 'Enable sound' : sound.blocked ? 'Click to unlock sound' : 'Sound on'}
        </Button>
      </div>
    </header>
  )
}

export default CarHeader
