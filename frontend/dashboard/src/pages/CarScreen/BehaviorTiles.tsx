import { cn } from '@/lib/utils'
import { BEHAVIORS, behaviorMeta } from './carMeta'

interface BehaviorTilesProps {
  /** `active_behaviors`: label → seconds. Driven by data, so labels the UI doesn't know still get a tile */
  active: Partial<Record<string, number>>
  /** The car is sounding its loud alarm (`response.sound` "high"): lit tiles turn danger instead of caution */
  alarm?: boolean
}

const formatSeconds = (s: number) => `${s < 10 ? s.toFixed(1) : Math.round(s)} s`

/** One tile per behaviour: the word, and the seconds it has lasted (Vigil: word and number, no icons) */
const BehaviorTiles = ({ active, alarm = false }: BehaviorTilesProps) => {
  const unknown = Object.keys(active).filter((id) => !BEHAVIORS.some((b) => b.id === id))
  const tiles = [...BEHAVIORS, ...unknown.map(behaviorMeta)]

  return (
    <section aria-label="Detected behaviours" className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
      {tiles.map(({ id, label }) => {
        const seconds = active[id]
        const lit = seconds !== undefined
        return (
          <div
            key={id}
            className={cn(
              'flex min-h-28 flex-col justify-between gap-4 rounded-md border p-4 transition-colors duration-300',
              !lit && 'bg-card',
              lit && (alarm ? 'border-danger bg-danger-soft text-danger' : 'border-caution bg-caution-soft text-caution'),
            )}
          >
            <span className={cn('text-label uppercase', !lit && 'text-muted-foreground')}>{label}</span>
            {lit ? (
              <span className="text-h2">{formatSeconds(seconds)}</span>
            ) : (
              <span className="text-h2 text-track">
                <span aria-hidden>--</span>
                <span className="sr-only">not detected</span>
              </span>
            )}
          </div>
        )
      })}
    </section>
  )
}

export default BehaviorTiles
