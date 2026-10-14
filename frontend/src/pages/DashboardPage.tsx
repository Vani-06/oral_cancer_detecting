import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { listPredictions } from '@/api/predictions'
import type { PredictionHistoryEntry } from '@/api/types'
import { PredictionBadge } from '@/components/result/PredictionBadge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'
import { useAuth } from '@/hooks/useAuth'
import { formatDateTime } from '@/lib/format'
import { AuthorizedImage } from '@/components/ui/AuthorizedImage'

export function DashboardPage() {
  const { user } = useAuth()
  const [items, setItems] = useState<PredictionHistoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    listPredictions()
      .then((result) => {
        if (!cancelled) setItems(result)
      })
      .catch((cause: unknown) => {
        if (cancelled) return
        setError(
          cause instanceof ApiError
            ? cause.detail
            : 'Dashboard data could not be loaded.',
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const summary = useMemo(() => {
    const total = items.length
    const pending = items.filter((item) => item.prediction === 'Pending').length
    const cancer = items.filter((item) => item.prediction === 'Cancer').length
    const nonCancer = items.filter((item) => item.prediction === 'Non-Cancer').length
    return { total, pending, cancer, nonCancer }
  }, [items])

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
          <p className="text-sm text-slate-600">Signed in as {user?.email}</p>
        </div>
        <Link to="/predict">
          <Button>New analysis</Button>
        </Link>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-10">
          <Spinner className="text-brand-600 h-6 w-6" label="Loading dashboard" />
        </div>
      ) : error ? (
        <Card title="Summary">
          <p
            role="alert"
            className="border-risk-high-border bg-risk-high-bg text-risk-high rounded-md border px-3 py-2 text-sm"
          >
            {error}
          </p>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard label="Total analyses" value={summary.total} />
            <SummaryCard label="Pending inference" value={summary.pending} />
            <SummaryCard label="Cancer" value={summary.cancer} />
            <SummaryCard label="Non-Cancer" value={summary.nonCancer} />
          </div>

          <Card
            title="Recent analyses"
            action={
              <Link to="/history" className="text-sm font-medium text-slate-600 underline">
                View all
              </Link>
            }
          >
            {items.length === 0 ? (
              <p className="text-sm text-slate-600">
                No analyses yet. Upload your first lesion image to begin.
              </p>
            ) : (
              <div className="space-y-3">
                {items.slice(0, 5).map((item) => (
                  <div
                    key={item.prediction_id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-200 p-3"
                  >
                    <div className="flex items-center gap-3">
                      {item.image_url ? (
                        <AuthorizedImage
                          src={item.image_url}
                          alt="Uploaded oral lesion"
                          className="h-12 w-12 rounded-md border border-slate-200 object-cover"
                        />
                      ) : null}
                      <div>
                        <p className="text-sm font-medium text-slate-900">
                          Prediction #{item.prediction_id}
                        </p>
                        <p className="text-xs text-slate-500">
                          {formatDateTime(item.created_at)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <PredictionBadge prediction={item.prediction} size="sm" />
                      <Link to={`/predictions/${item.prediction_id}`}>
                        <Button variant="secondary" size="sm">
                          Open
                        </Button>
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  )
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <div className="flex flex-col gap-1">
        <span className="text-sm text-slate-500">{label}</span>
        <span className="text-2xl font-semibold text-slate-900">{value}</span>
      </div>
    </Card>
  )
}
