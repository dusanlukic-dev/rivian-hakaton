import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import type { Behavior } from '@/api/types'
import { endTrip, errorMessage, httpStatus, localIsoTimestamp, postTelemetry, startTrip } from '@/api/trips'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { BEHAVIORS } from './carMeta'
import Chip from './Chip'

const DRIVER_ID = 'dashboard-demo'
const TICK_MS = 1000

interface SimulatorPanelProps {
  /** The live trip's id (from the WebSocket), for "End trip" */
  tripId: string | null
}

/**
 * Dev stand-in for the camera models: POST /telemetry every second while "Running" is on.
 * A proposal, not yet agreed with the backend owner (.claude/knowledge/contract-notes.md).
 */
const SimulatorPanel = ({ tripId }: SimulatorPanelProps) => {
  // `?sim` in the URL opens it on load
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).has('sim'))
  const [running, setRunning] = useState(false)
  const [speed, setSpeed] = useState(60)
  const [behaviors, setBehaviors] = useState<Behavior[]>([])
  const [hint, setHint] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // The interval reads the latest controls without restarting
  const latest = useRef({ speed, behaviors })
  useEffect(() => {
    latest.current = { speed, behaviors }
  })

  useEffect(() => {
    if (!running) return
    let cancelled = false
    const tick = async () => {
      try {
        const { speed: speed_kmh, behaviors } = latest.current
        await postTelemetry({ timestamp: localIsoTimestamp(), speed_kmh, behaviors })
        if (!cancelled) setHint(null)
      } catch (error) {
        if (cancelled) return
        setHint(httpStatus(error) === 409 ? 'No active trip (409): press "Start trip" first.' : `Telemetry failed: ${errorMessage(error)}`)
      }
    }
    const timer = setInterval(tick, TICK_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [running])

  const start = async () => {
    setBusy(true)
    try {
      await startTrip({ driver_id: DRIVER_ID })
      setHint(null)
    } catch (error) {
      toast.error(`Start trip failed: ${errorMessage(error)}`)
    } finally {
      setBusy(false)
    }
  }

  const end = async () => {
    if (!tripId) return
    setBusy(true)
    setRunning(false)
    try {
      await endTrip(tripId)
    } catch (error) {
      toast.error(`End trip failed: ${errorMessage(error)}`)
    } finally {
      setBusy(false)
    }
  }

  const toggle = (id: Behavior) =>
    setBehaviors((list) => (list.includes(id) ? list.filter((b) => b !== id) : [...list, id]))

  return (
    <Card className="gap-0 p-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex min-h-16 w-full items-center gap-3 rounded-lg px-6 py-4 text-left"
      >
        <span className="text-h3">Simulator</span>
        <Chip>Dev</Chip>
        <Chip>Proposal</Chip>
        {running && <Chip tone="safe">Running</Chip>}
        <span className="ml-auto text-label text-muted-foreground uppercase">{open ? 'Hide' : 'Show'}</span>
      </button>

      {open && (
        <div className="flex flex-col gap-6 border-t px-6 py-6">
          <p className="text-body-sm text-muted-foreground">
            Stands in for the camera models: sends <code>POST /telemetry</code> every second while running. A proposal, not yet agreed with
            the backend owner.
          </p>

          <div className="grid grid-cols-2 gap-3">
            <Button size="lg" className="h-12 text-body-sm" onClick={start} disabled={busy}>
              Start trip
            </Button>
            <Button size="lg" variant="outline" className="h-12 text-body-sm" onClick={end} disabled={busy || !tripId}>
              End trip
            </Button>
          </div>

          <div className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between">
              <Label htmlFor="sim-speed" className="text-label text-muted-foreground uppercase">
                Speed
              </Label>
              <span className="text-body-sm">{speed} km/h</span>
            </div>
            <input
              id="sim-speed"
              type="range"
              min={0}
              max={150}
              step={5}
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
              className="w-full accent-primary"
            />
          </div>

          <div className="flex flex-col gap-3">
            <span className="text-label text-muted-foreground uppercase">Behaviours</span>
            <div className="grid grid-cols-2 gap-2">
              {BEHAVIORS.map(({ id, label }) => {
                const on = behaviors.includes(id)
                return (
                  <Button
                    key={id}
                    variant="outline"
                    aria-pressed={on}
                    onClick={() => toggle(id)}
                    className={cn(
                      'h-auto min-h-11 justify-start px-3 py-2 text-left text-body-sm whitespace-normal',
                      on ? 'border-caution bg-caution-soft text-caution hover:bg-caution-soft hover:text-caution' : 'border-border',
                    )}
                  >
                    {label}
                  </Button>
                )
              })}
            </div>
          </div>

          <Label className="gap-3 text-body-sm">
            <Switch checked={running} onCheckedChange={setRunning} />
            Running (1 tick/s)
          </Label>

          {hint && <p className="rounded-md border border-caution bg-caution-soft px-4 py-3 text-body-sm text-caution">{hint}</p>}
        </div>
      )}
    </Card>
  )
}

export default SimulatorPanel
