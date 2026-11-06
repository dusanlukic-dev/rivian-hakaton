import { HugeiconsIcon } from '@hugeicons/react'
import { Cancel01Icon, CheckmarkCircle02Icon } from '@hugeicons/core-free-icons'
import type { TripSummary } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { behaviorMeta, formatDuration, formatScore, levelLabel, LEVELS, lightColor } from './carMeta'
import { DriveReport } from './DriveReport'

interface TripSummaryCardProps {
  summary: TripSummary
  onDismiss: () => void
}

const Stat = ({ label, value, color }: { label: string; value: number; color?: string }) => (
  <div className="flex flex-col gap-1 rounded-lg bg-muted/50 p-4">
    <span className="text-xs tracking-widest text-muted-foreground uppercase">{label}</span>
    <span className="text-4xl font-bold tabular-nums" style={color ? { color } : undefined}>{formatScore(value)}</span>
  </div>
)

/** Shown on `trip_ended`: average (while driving) / lowest score and the behaviours with tips (worst first) */
const TripSummaryCard = ({ summary, onDismiss }: TripSummaryCardProps) => (
  <Card className="gap-5 p-6 text-sm">
    <div className="flex items-start gap-4">
      <div>
        <h2 className="text-xl font-bold">Trip summary</h2>
        <p className="text-muted-foreground">
          Driver {summary.driver_id} · {formatDuration(summary.duration_s)} · {levelLabel(summary.level)}
          {summary.emergency_alert_sent && ' · emergency alert sent'}
        </p>
      </div>
      <Button variant="ghost" size="icon" className="ml-auto" aria-label="Close summary" onClick={onDismiss}>
        <HugeiconsIcon icon={Cancel01Icon} />
      </Button>
    </div>

    <div className="grid grid-cols-2 gap-3">
      <Stat label="Average while driving" value={summary.average_score} color={lightColor(LEVELS.find((l) => l.id === summary.level)?.light)} />
      <Stat label="Lowest" value={summary.min_score} />
    </div>

    <DriveReport tripId={summary.trip_id} />

    {summary.behaviors.length === 0 ? (
      <p className="flex items-center gap-2 text-base">
        <HugeiconsIcon icon={CheckmarkCircle02Icon} className="text-lamp-green" />
        Clean drive: no risky behaviour detected.
      </p>
    ) : (
      <ul className="flex flex-col gap-2">
        {summary.behaviors.map((b) => {
          const meta = behaviorMeta(b.behavior)
          return (
            <li key={b.behavior} className="flex items-start gap-3 rounded-lg bg-muted/50 p-3">
              <HugeiconsIcon icon={meta.icon} size={22} className="mt-0.5 shrink-0 text-lamp-yellow" />
              <div className="min-w-0">
                <p className="font-semibold">
                  {meta.label}
                  <span className="font-normal text-muted-foreground">
                    {' · '}{b.occurrences}× · {Math.round(b.total_seconds)} s
                  </span>
                </p>
                <p className="text-muted-foreground">{b.tip}</p>
              </div>
            </li>
          )
        })}
      </ul>
    )}
  </Card>
)

export default TripSummaryCard
