import type { CSSProperties } from 'react'
import type { TripState } from '@/api/types'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { formatScore, levelLabel, LEVELS, lightColor } from './carMeta'

interface StatusPanelProps {
  trip: TripState | null
  /** Connection lost: dim the last known state */
  stale: boolean
}

/** The car's lamp (`response.dashboard_light`), the score gauge, the level and `response.message` */
const StatusPanel = ({ trip, stale }: StatusPanelProps) => {
  const lamp = trip ? lightColor(trip.response.dashboard_light) : null
  const levelIndex = trip ? LEVELS.findIndex((l) => l.id === trip.level) : -1
  const style = { '--lamp': lamp ?? 'var(--muted-foreground)' } as CSSProperties

  return (
    <Card
      className={cn('grid items-center gap-8 p-6 text-sm md:grid-cols-[auto_auto_minmax(0,1fr)]', stale && 'opacity-60')}
      style={style}
    >
      <div className="flex flex-col items-center gap-3">
        <div
          role="img"
          aria-label={trip ? `Dashboard light: ${trip.response.dashboard_light}` : 'Dashboard light off'}
          className="size-40 rounded-full ring-4 ring-foreground/10 transition-[background,box-shadow] duration-500"
          style={
            lamp
              ? {
                  background: `radial-gradient(circle at 35% 30%, color-mix(in oklch, ${lamp} 45%, white), ${lamp} 55%, color-mix(in oklch, ${lamp} 65%, black))`,
                  boxShadow: `0 0 70px 10px color-mix(in oklch, ${lamp} 45%, transparent)`,
                }
              : { background: 'radial-gradient(circle at 35% 30%, var(--secondary), var(--muted) 60%)' }
          }
        />
        <span className="text-xs tracking-widest text-muted-foreground uppercase">Dashboard light</span>
      </div>

      <div className="relative mx-auto grid size-48 place-items-center">
        <svg viewBox="0 0 200 200" className="absolute inset-0 -rotate-90" aria-hidden>
          <circle cx="100" cy="100" r="88" fill="none" strokeWidth="12" className="stroke-muted" />
          {trip && (
            <circle
              cx="100"
              cy="100"
              r="88"
              fill="none"
              strokeWidth="12"
              strokeLinecap="round"
              pathLength={100}
              strokeDasharray={`${trip.score} 100`}
              style={{ stroke: 'var(--lamp)', transition: 'stroke-dasharray 0.6s ease' }}
            />
          )}
        </svg>
        <div className="flex flex-col items-center">
          <span className="text-5xl font-bold tabular-nums">{trip ? formatScore(trip.score) : '--'}</span>
          <span className="text-xs text-muted-foreground">score / 100</span>
        </div>
      </div>

      <div className="flex min-w-0 flex-col gap-5">
        <div>
          <span className="text-xs tracking-widest text-muted-foreground uppercase">Level</span>
          <p className="text-3xl font-bold" style={trip ? { color: 'var(--lamp)' } : undefined}>
            {trip ? levelLabel(trip.level) : 'No active trip'}
          </p>
        </div>

        <div className="grid grid-cols-6 gap-1.5" aria-label={trip ? `Level ${levelIndex + 1} of 6` : 'No level'}>
          {LEVELS.map((level, i) => (
            <div key={level.id} className="flex min-w-0 flex-col gap-1.5">
              <div
                className={cn(
                  'h-3 rounded-full transition-opacity duration-500',
                  i <= levelIndex ? 'opacity-100' : 'opacity-15',
                  i === levelIndex && 'ring-2 ring-foreground/70 ring-offset-2 ring-offset-card',
                )}
                style={{ background: lightColor(level.light) }}
              />
              <span
                className={cn(
                  'truncate text-[10px] tracking-wide uppercase',
                  i === levelIndex ? 'font-semibold text-foreground' : 'text-muted-foreground',
                )}
              >
                {level.label}
              </span>
            </div>
          ))}
        </div>

        <p className="border-l-4 py-1 pl-3 text-lg leading-snug" style={{ borderColor: 'var(--lamp)' }}>
          {trip ? trip.response.message : 'Start a trip from the phone app, or with the simulator.'}
        </p>
      </div>
    </Card>
  )
}

export default StatusPanel
