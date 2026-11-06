import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { TripSummary } from '@/api/types'
import { getReport, errorMessage } from '@/api/trips'
import TripSummaryCard from '@/pages/CarScreen/TripSummaryCard'

/** /trip/:id: any stored trip's summary and drive chart (GET /trips/{id}/report), e.g. after the car screen was closed */
const TripReportPage = () => {
  const { id = '' } = useParams()
  const [summary, setSummary] = useState<TripSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getReport(id)
      .then((r) => { if (!cancelled) setSummary(r.trip) })
      .catch((e: unknown) => { if (!cancelled) setError(errorMessage(e)) })
    return () => { cancelled = true }
  }, [id])

  return (
    <main className="mx-auto flex min-h-dvh max-w-5xl flex-col gap-6 p-4 text-foreground sm:p-6 lg:p-8">
      <Link to="/" className="self-start text-label text-muted-foreground uppercase hover:text-foreground">← Car screen</Link>
      {error && <p className="rounded-md border border-danger bg-danger-soft px-4 py-3 text-body-sm text-danger">{error}</p>}
      {summary && <TripSummaryCard summary={summary} onDismiss={() => history.back()} />}
    </main>
  )
}

export default TripReportPage
