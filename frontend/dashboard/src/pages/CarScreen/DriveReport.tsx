import { useEffect, useState } from 'react'
import type { DangerLevel, DangerMoment, TripReport, TripSection } from '@/api/types'
import { getReport, httpStatus } from '@/api/trips'
import { behaviorMeta, formatDuration, formatScore } from './carMeta'

/** The backend decides the danger (docs/API.md §4 DangerLevel); these are only its colours */
const DANGER_COLOR: Record<DangerLevel, string> = { none: '#737373', dangerous: '#F59E0B', critical: '#EF4444' }

// Drawn in a fixed coordinate space and scaled with the card (viewBox), text included
const W = 720
const LEFT = 34
const RIGHT = 12
const PLOT_H = 190
const BOTTOM = 24
const BOX_W = 96
const BOX_H = 72
const BOX_SPACE = 2 * BOX_H + 8 + 18

interface Box {
  moment: DangerMoment
  x: number
  y: number
  center: number
}

function layoutBoxes(moments: DangerMoment[], xOf: (t: number) => number): Box[] {
  const rowEnds = [-Infinity, -Infinity]
  const boxes: Box[] = []
  for (const moment of moments.filter((m) => m.danger === 'critical' && m.image_url).sort((a, b) => a.peak_t - b.peak_t)) {
    const center = Math.min(Math.max(xOf(moment.peak_t), LEFT + BOX_W / 2), W - RIGHT - BOX_W / 2)
    const x = center - BOX_W / 2
    const row = rowEnds.findIndex((end) => x >= end + 8)
    if (row === -1) continue // both rows taken here: the node stays, without a picture
    rowEnds[row] = x + BOX_W
    boxes.push({ moment, x, y: BOX_SPACE - 14 - BOX_H - row * (BOX_H + 8), center })
  }
  return boxes
}

/** Score over the trip, dangerous sections shaded, a node per dangerous moment, pictures above the critical ones */
export function DriveChart({ sections, moments, onSelect, selected }: {
  sections: TripSection[]
  moments: DangerMoment[]
  onSelect: (m: DangerMoment) => void
  selected: DangerMoment | null
}) {
  const hasBoxes = moments.some((m) => m.danger === 'critical' && m.image_url)
  const top = hasBoxes ? BOX_SPACE : 12
  const height = top + PLOT_H + BOTTOM
  const tMax = Math.max(sections.at(-1)?.t_end ?? 0, ...moments.map((m) => m.t_end), 1)
  const x = (t: number) => LEFT + (Math.min(Math.max(t, 0), tMax) / tMax) * (W - LEFT - RIGHT)
  const y = (score: number) => top + (1 - Math.min(Math.max(score, 0), 100) / 100) * PLOT_H
  const points: [number, number][] = [[0, sections[0]?.score_start ?? 100], ...sections.map((s): [number, number] => [s.t_end, s.score_end])]
  const line = points.map(([t, s], i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(s).toFixed(1)}`).join(' ')
  const area = `${line} L${x(points[points.length - 1][0]).toFixed(1)},${y(0)} L${x(0)},${y(0)} Z`
  const boxes = layoutBoxes(moments, x)

  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="h-auto w-full select-none" role="img" aria-label="Score over the drive">
      <defs>
        <linearGradient id="drive-score" x1="0" y1={y(100)} x2="0" y2={y(0)} gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#22C55E" stopOpacity="0.35" />
          <stop offset="0.45" stopColor="#FACC15" stopOpacity="0.22" />
          <stop offset="1" stopColor="#EF4444" stopOpacity="0.3" />
        </linearGradient>
        <clipPath id="drive-box">
          <rect width={BOX_W} height={BOX_H} rx="8" />
        </clipPath>
      </defs>
      {sections.filter((s) => s.danger !== 'none').map((s) => (
        <rect key={s.section_id} x={x(s.t_start)} y={top} width={Math.max(x(s.t_end) - x(s.t_start), 1.5)} height={PLOT_H}
          fill={DANGER_COLOR[s.danger]} opacity={s.danger === 'critical' ? 0.24 : 0.14} />
      ))}
      {[100, 75, 50, 25, 0].map((v) => (
        <g key={v}>
          <line x1={LEFT} x2={W - RIGHT} y1={y(v)} y2={y(v)} stroke="currentColor" strokeOpacity="0.1" />
          <text x={LEFT - 8} y={y(v) + 4} fontSize="11" textAnchor="end" fill="currentColor" fillOpacity="0.5">{v}</text>
        </g>
      ))}
      <path d={area} fill="url(#drive-score)" />
      <path d={line} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" />
      {boxes.map((b) => (
        <line key={`c${b.moment.moment_id}`} x1={b.center} y1={b.y + BOX_H} x2={x(b.moment.peak_t)} y2={y(b.moment.peak_score)}
          stroke={DANGER_COLOR.critical} strokeWidth="1.5" strokeDasharray="4 3" />
      ))}
      {moments.map((m) => (
        <circle key={m.moment_id} cx={x(m.peak_t)} cy={y(m.peak_score)} r={m.danger === 'critical' ? 7 : 5}
          fill={DANGER_COLOR[m.danger]} stroke={selected?.moment_id === m.moment_id ? 'currentColor' : 'var(--background, #0a0a0a)'}
          strokeWidth="2.5" className="cursor-pointer" onClick={() => onSelect(m)}>
          <title>{`${formatDuration(m.peak_t)}: ${Object.keys(m.behaviors).map((k) => behaviorMeta(k).label).join(', ') || 'camera alarm'}`}</title>
        </circle>
      ))}
      {boxes.map((b) => (
        <g key={`b${b.moment.moment_id}`} transform={`translate(${b.x},${b.y})`} className="cursor-pointer" onClick={() => onSelect(b.moment)}>
          <image href={b.moment.image_url ?? undefined} width={BOX_W} height={BOX_H} preserveAspectRatio="xMidYMid slice" clipPath="url(#drive-box)" />
          <rect width={BOX_W} height={BOX_H} rx="8" fill="none" stroke={DANGER_COLOR.critical} strokeWidth="2" />
        </g>
      ))}
      <text x={LEFT} y={top + PLOT_H + 17} fontSize="11" fill="currentColor" fillOpacity="0.5">0:00</text>
      <text x={W - RIGHT} y={top + PLOT_H + 17} fontSize="11" textAnchor="end" fill="currentColor" fillOpacity="0.5">{formatDuration(tMax)}</text>
    </svg>
  )
}

function MomentDetail({ moment }: { moment: DangerMoment }) {
  const behaviors = Object.entries(moment.behaviors)
  return (
    <div className="flex flex-col gap-3 rounded-lg bg-muted/50 p-3 sm:flex-row">
      {moment.image_url && (
        <img src={moment.image_url} alt="The camera at that moment" className="w-full rounded-md object-cover sm:w-56" />
      )}
      <div className="flex min-w-0 flex-col gap-1">
        <p className="font-semibold" style={{ color: DANGER_COLOR[moment.danger] }}>
          {moment.danger === 'critical' ? 'Critical' : 'Dangerous'} · {formatDuration(moment.t_start)}–{formatDuration(moment.t_end)}
        </p>
        <p>{behaviors.length ? behaviors.map(([k, s]) => `${behaviorMeta(k).label} ${(s ?? 0).toFixed(1)} s`).join(' · ') : 'Camera alarm'}</p>
        <p className="text-muted-foreground">
          −{moment.score_drop.toFixed(1)} points ({formatScore(moment.score_start)} → {formatScore(moment.score_min)})
          {' · '}{Math.round(moment.speed_avg_kmh)} km/h
          {moment.rules_triggered.length > 0 && ` · ${moment.rules_triggered.map((r) => r.replace(/_/g, ' ')).join(', ')}`}
        </p>
      </div>
    </div>
  )
}

/** GET /trips/{id}/report for the summary card. Hidden when storage is down (503), the trip wasn't stored, or it
 * belongs to a logged-in driver (404: their report is private to their account, the phone shows it) */
export function DriveReport({ tripId }: { tripId: string }) {
  const [report, setReport] = useState<TripReport | null>(null)
  const [selected, setSelected] = useState<DangerMoment | null>(null)

  useEffect(() => {
    let cancelled = false
    getReport(tripId)
      .then((r) => { if (!cancelled) setReport(r) })
      .catch((e: unknown) => { if (!cancelled && ![404, 503].includes(httpStatus(e) ?? 0)) console.warn('[report]', e) })
    return () => { cancelled = true }
  }, [tripId])

  if (!report || report.sections.length === 0) return null
  const critical = report.moments.filter((m) => m.danger === 'critical').length
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-baseline gap-3">
        <h3 className="font-semibold">Your drive</h3>
        <span className="text-xs text-muted-foreground">
          {report.moments.length} dangerous moment{report.moments.length === 1 ? '' : 's'}{critical ? `, ${critical} critical` : ''} · click a dot or a picture
        </span>
      </div>
      <DriveChart sections={report.sections} moments={report.moments} onSelect={setSelected} selected={selected} />
      {selected && <MomentDetail moment={selected} />}
    </section>
  )
}
