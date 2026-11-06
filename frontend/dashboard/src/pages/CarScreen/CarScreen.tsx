import BehaviorTiles from './BehaviorTiles'
import CarHeader from './CarHeader'
import CarIndicators from './CarIndicators'
import ConnectPhoneCard from './ConnectPhoneCard'
import EmergencyOverlay from './EmergencyOverlay'
import SimulatorPanel from './SimulatorPanel'
import StatusPanel from './StatusPanel'
import TripSummaryCard from './TripSummaryCard'
import { useCarScreen } from './useCarScreen'

/** `/`: mock of the car's centre screen. Executes the backend's `response` for the live trip (docs/API.md §7) */
const CarScreen = () => {
  const { status, trip, summary, emergency, dismissEmergency, dismissSummary, sound } = useCarScreen()
  const stale = !!trip && status !== 'open'
  const alarm = !stale && trip?.response.sound === 'high'

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <CarHeader status={status} trip={trip} sound={sound} />

      <main className="mx-auto grid w-full max-w-[1600px] gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_24rem] lg:p-6">
        <div className="flex min-w-0 flex-col gap-4">
          {summary && <TripSummaryCard summary={summary} onDismiss={dismissSummary} />}
          <StatusPanel trip={trip} stale={stale} />
          <BehaviorTiles active={trip?.active_behaviors ?? {}} />
          <CarIndicators response={trip?.response ?? null} soundOn={sound.on} />
          {stale && <p className="text-sm text-muted-foreground">Connection lost: showing the last known state while reconnecting.</p>}
        </div>

        <aside className="flex flex-col gap-4">
          <ConnectPhoneCard />
          <SimulatorPanel tripId={trip?.trip_id ?? null} />
        </aside>
      </main>

      {/* sound "high": red edge pulse at 1 Hz (≤ 2 Hz) */}
      {alarm && (
        <div
          aria-hidden
          className="pointer-events-none fixed inset-0 z-40 animate-alarm-pulse"
          style={{ boxShadow: 'inset 0 0 9rem 1rem color-mix(in oklch, var(--lamp-red) 65%, transparent)' }}
        />
      )}
      {emergency && <EmergencyOverlay trip={emergency} soundOn={sound.on} onDismiss={dismissEmergency} />}
    </div>
  )
}

export default CarScreen
