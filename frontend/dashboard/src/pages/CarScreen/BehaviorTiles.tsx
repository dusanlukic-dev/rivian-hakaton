import { HugeiconsIcon } from '@hugeicons/react'
import { cn } from '@/lib/utils'
import { BEHAVIORS, behaviorMeta } from './carMeta'

interface BehaviorTilesProps {
  /** `active_behaviors`: label → seconds. Driven by data, so labels the UI doesn't know still get a tile */
  active: Partial<Record<string, number>>
}

const formatSeconds = (s: number) => `${s < 10 ? s.toFixed(1) : Math.round(s)} s`

const BehaviorTiles = ({ active }: BehaviorTilesProps) => {
  const unknown = Object.keys(active).filter((id) => !BEHAVIORS.some((b) => b.id === id))
  const tiles = [...BEHAVIORS, ...unknown.map(behaviorMeta)]

  return (
    <section aria-label="Detected behaviours" className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
      {tiles.map(({ id, label, icon }) => {
        const seconds = active[id]
        const lit = seconds !== undefined
        return (
          <div
            key={id}
            className={cn(
              'flex flex-col items-center gap-2 rounded-lg p-4 text-center ring-1 transition-colors duration-300',
              lit ? 'bg-lamp-yellow/15 text-foreground ring-lamp-yellow' : 'bg-card text-muted-foreground ring-foreground/10',
            )}
          >
            <HugeiconsIcon icon={icon} size={32} className={lit ? 'text-lamp-yellow' : 'opacity-40'} />
            <span className="text-sm font-medium">{label}</span>
            <span className={cn('font-mono text-xs tabular-nums', !lit && 'invisible')}>
              {lit ? formatSeconds(seconds) : '0 s'}
            </span>
          </div>
        )
      })}
    </section>
  )
}

export default BehaviorTiles
