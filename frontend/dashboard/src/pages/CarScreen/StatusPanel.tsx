import type { CSSProperties } from 'react'
import type { TripState } from '@/api/types'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { formatScore, levelLabel, LEVELS, lightColor, lightName, lightSoftColor } from './carMeta'

interface StatusPanelProps {
  trip: TripState | null
  /** Connection lost: dim the last known state */
  stale: boolean
}

/**
 * Vigil ScoreRing (the hero: a thin ring, the score in the middle, the state word below), the level, the car's lamp
 * (`response.dashboard_light`) and `response.message` as an alert
 */
const StatusPanel = ({ trip, stale }: StatusPanelProps) => {
  const light = trip?.response.dashboard_light
  const levelIndex = trip ? LEVELS.findIndex((l) => l.id === trip.level) : -1
  const style = {
    '--lamp': trip ? lightColor(light) : 'var(--muted-foreground)',
    '--lamp-soft': trip ? lightSoftColor(light) : 'var(--muted)',
  } as CSSProperties

  return (
    <Card className={cn('grid items-center gap-8 p-6 lg:p-8 xl:grid-cols-[auto_minmax(0,1fr)]', stale && 'opacity-60')} style={style}>
      {/* Ring: stroke 10 on 160 (Vigil), drawn at 272px so a 4-digit score-xl number fits */}
      <div className="relative mx-auto grid size-68 place-items-center">
        <svg viewBox="0 0 160 160" className="absolute inset-0 -rotate-90" aria-hidden>
          <circle cx="80" cy="80" r="70" className="fill-muted" />
          <circle cx="80" cy="80" r="75" fill="none" strokeWidth="10" className="stroke-track" />
          {trip && (
            <circle
              cx="80"
              cy="80"
              r="75"
              fill="none"
              strokeWidth="10"
              strokeLinecap="round"
              pathLength={100}
              strokeDasharray={`${trip.score} 100`}
              style={{ stroke: 'var(--lamp)', transition: 'stroke-dasharray 300ms ease-out, stroke 300ms ease-out' }}
            />
          )}
        </svg>
        <div className="relative flex flex-col items-center gap-2">
          <span className={cn('text-score-xl', !trip && 'text-muted-foreground')}>{trip ? formatScore(trip.score) : '--'}</span>
          <span className="text-label uppercase" style={{ color: 'var(--lamp)' }}>
            {trip ? levelLabel(trip.level) : 'No trip'}
          </span>
        </div>
      </div>

      <div className="flex min-w-0 flex-col gap-6">
        {/* The car's dashboard lamp: flat state colour with a -soft halo, and the light written as a word */}
        <div className="flex items-center gap-6">
          <div
            role="img"
            aria-label={trip ? `Dashboard light: ${lightName(light)}` : 'Dashboard light off'}
            className="m-2 size-20 shrink-0 rounded-full transition-[background-color,box-shadow] duration-300"
            style={
              trip
                ? { background: 'var(--lamp)', boxShadow: '0 0 0 8px var(--lamp-soft)' }
                : { background: 'var(--muted)', boxShadow: '0 0 0 1px var(--line)' }
            }
          />
          <div className="flex min-w-0 flex-col gap-1">
            <span className="text-label text-muted-foreground uppercase">Dashboard light</span>
            <p className="text-h1" style={trip ? { color: 'var(--lamp)' } : { color: 'var(--muted-foreground)' }}>
              {trip ? lightName(light) : 'Off'}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-6 gap-2" aria-label={trip ? `Level ${levelIndex + 1} of 6: ${levelLabel(trip.level)}` : 'No level'}>
          {LEVELS.map((level, i) => (
            <div key={level.id} className="flex min-w-0 flex-col gap-2">
              <div
                className={cn('h-2 rounded-full transition-colors duration-300', i > levelIndex && 'bg-track')}
                style={i <= levelIndex ? { background: lightColor(level.light) } : undefined}
              />
              <span className={cn('truncate text-label uppercase', i === levelIndex ? 'text-foreground' : 'text-muted-foreground')}>
                {level.label}
              </span>
            </div>
          ))}
        </div>

        <p
          className="rounded-md border px-5 py-4 text-h3"
          style={trip ? { background: 'var(--lamp-soft)', borderColor: 'var(--lamp)', color: 'var(--lamp)' } : undefined}
        >
          {trip ? trip.response.message : 'Start a trip from the phone app, or with the simulator.'}
        </p>
      </div>
    </Card>
  )
}

export default StatusPanel
