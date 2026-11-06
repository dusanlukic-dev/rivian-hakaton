import { useEffect, useRef, useState } from 'react'
import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowDown01Icon, DashboardSpeed01Icon, PlayIcon, StopIcon, TestTube01Icon } from '@hugeicons/core-free-icons'
import { toast } from 'sonner'
import type { Behavior } from '@/api/types'
import { endTrip, errorMessage, httpStatus, localIsoTimestamp, postTelemetry, startTrip } from '@/api/trips'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { BEHAVIORS } from './carMeta'

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
    <Card className="gap-0 p-0 text-sm">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-5 py-4 text-left"
      >
        <HugeiconsIcon icon={TestTube01Icon} size={18} />
        <span className="font-semibold">Simulator (dev)</span>
        <Badge variant="outline">Proposal</Badge>
        {running && <Badge className="bg-lamp-green/15 text-lamp-green">Running</Badge>}
        <HugeiconsIcon icon={ArrowDown01Icon} size={16} className={cn('ml-auto transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="flex flex-col gap-4 border-t px-5 py-4">
          <p className="text-xs text-muted-foreground">
            Stands in for the camera models: sends <code>POST /telemetry</code> every second while running. A proposal, not yet agreed with
            the backend owner.
          </p>

          <div className="grid grid-cols-2 gap-2">
            <Button size="lg" onClick={start} disabled={busy}>
              <HugeiconsIcon icon={PlayIcon} />
              Start trip
            </Button>
            <Button size="lg" variant="outline" onClick={end} disabled={busy || !tripId}>
              <HugeiconsIcon icon={StopIcon} />
              End trip
            </Button>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs">
              <Label htmlFor="sim-speed" className="gap-1.5">
                <HugeiconsIcon icon={DashboardSpeed01Icon} size={14} />
                Speed
              </Label>
              <span className="font-mono tabular-nums">{speed} km/h</span>
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

          <div className="flex flex-col gap-1.5">
            <span className="text-xs text-muted-foreground">Behaviours</span>
            <div className="grid grid-cols-2 gap-1.5">
              {BEHAVIORS.map(({ id, label, icon }) => {
                const on = behaviors.includes(id)
                return (
                  <Button
                    key={id}
                    variant={on ? 'secondary' : 'ghost'}
                    aria-pressed={on}
                    onClick={() => toggle(id)}
                    className={cn('justify-start ring-1', on ? 'ring-lamp-yellow' : 'ring-foreground/10')}
                  >
                    <HugeiconsIcon icon={icon} className={on ? 'text-lamp-yellow' : undefined} />
                    <span className="truncate">{label}</span>
                  </Button>
                )
              })}
            </div>
          </div>

          <Label className="gap-2 text-sm">
            <Switch checked={running} onCheckedChange={setRunning} />
            Running (1 tick/s)
          </Label>

          {hint && <p className="rounded-md bg-lamp-yellow/15 px-3 py-2 text-xs text-foreground ring-1 ring-lamp-yellow/50">{hint}</p>}
        </div>
      )}
    </Card>
  )
}

export default SimulatorPanel
