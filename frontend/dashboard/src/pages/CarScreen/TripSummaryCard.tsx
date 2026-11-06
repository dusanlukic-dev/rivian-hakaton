import type { TripSummary } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { behaviorMeta, formatDuration, formatScore, levelColor, levelLabel } from './carMeta'
import { DriveReport } from './DriveReport'

interface TripSummaryCardProps {
  summary: TripSummary
  onDismiss: () => void
}

const Stat = ({ label, value, color }: { label: string; value: number; color?: string }) => (
  <div className="flex flex-col gap-2 rounded-md bg-muted p-4">
    <span className="text-label text-muted-foreground uppercase">{label}</span>
    <span className="text-h1" style={color ? { color } : undefined}>
      {formatScore(value)}
    </span>
  </div>
)

/** Shown on `trip_ended` (Vigil TripReport): final / average / lowest score, the drive chart and the behaviours with tips */
const TripSummaryCard = ({ summary, onDismiss }: TripSummaryCardProps) => (
  <Card className="gap-6 p-6 lg:p-8">
    <div className="flex items-start gap-4">
      <div className="flex min-w-0 flex-col gap-1">
        <h2 className="text-h2">Trip summary</h2>
        <p className="text-body-sm text-muted-foreground">
          Driver {summary.driver_id} · {formatDuration(summary.duration_s)} · {levelLabel(summary.level)}
          {summary.emergency_alert_sent && ' · emergency alert sent'}
        </p>
      </div>
      <Button variant="outline" size="lg" className="ml-auto h-10 px-4 text-body-sm" onClick={onDismiss}>
        Close
      </Button>
    </div>

    <div className="grid grid-cols-3 gap-4">
      <Stat label="Final score" value={summary.final_score} color={levelColor(summary.level)} />
      <Stat label="Average" value={summary.average_score} />
      <Stat label="Lowest" value={summary.min_score} />
    </div>

    <DriveReport tripId={summary.trip_id} />

    {summary.behaviors.length === 0 ? (
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-md bg-safe-soft px-4 py-3 text-safe">
        <span className="text-label uppercase">Clean drive</span>
        <span className="text-body-sm">No risky behaviour detected.</span>
      </p>
    ) : (
      <section className="flex flex-col gap-3">
        <h3 className="text-label text-muted-foreground uppercase">Behaviours, worst first</h3>
        <ul className="flex flex-col gap-2">
          {summary.behaviors.map((b) => (
            <li key={b.behavior} className="flex flex-col gap-1 rounded-md border p-4">
              <p className="flex flex-wrap items-baseline gap-x-3">
                <span className="text-body font-semibold">{behaviorMeta(b.behavior).label}</span>
                <span className="text-body-sm text-muted-foreground">
                  {b.occurrences}× · {Math.round(b.total_seconds)} s
                </span>
              </p>
              <p className="text-body-sm text-muted-foreground">{b.tip}</p>
            </li>
          ))}
        </ul>
      </section>
    )}
  </Card>
)

export default TripSummaryCard
