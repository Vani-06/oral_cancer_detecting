import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { listPredictions } from '@/api/predictions'
import type { PredictionHistoryEntry } from '@/api/types'
import { GradeBadge } from '@/components/result/GradeBadge'
import { PredictionBadge } from '@/components/result/PredictionBadge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'
import { formatDateTime } from '@/lib/format'
import { AuthorizedImage } from '@/components/ui/AuthorizedImage'

export function HistoryPage() {
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
            : 'Prediction history could not be loaded.',
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">History</h1>
          <p className="text-sm text-slate-600">
            Review previous analyses and reopen stored results.
          </p>
        </div>
        <Link to="/predict">
          <Button>New analysis</Button>
        </Link>
      </div>

      <Card title="Previous analyses">
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Spinner className="text-brand-600 h-6 w-6" label="Loading history" />
          </div>
        ) : error ? (
          <div className="flex flex-col gap-3">
            <p
              role="alert"
              className="border-risk-high-border bg-risk-high-bg text-risk-high rounded-md border px-3 py-2 text-sm"
            >
              {error}
            </p>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col gap-3 py-4">
            <p className="text-sm text-slate-600">
              No analyses yet. Upload your first lesion image to begin.
            </p>
            <div>
              <Link to="/predict">
                <Button size="sm">Start first analysis</Button>
              </Link>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="py-3 pr-4 font-medium">Image</th>
                  <th className="py-3 pr-4 font-medium">Dysplasia grade</th>
                  <th className="py-3 pr-4 font-medium">Cancer detection</th>
                  <th className="py-3 pr-4 font-medium">Created</th>
                  <th className="py-3 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item) => (
                  <tr key={item.prediction_id} className="align-middle">
                    <td className="py-3 pr-4">
                      {item.image_url ? (
                        <AuthorizedImage
                          src={item.image_url}
                          alt="Uploaded oral lesion"
                          className="h-14 w-14 rounded-md border border-slate-200 object-cover"
                        />
                      ) : (
                        <div className="flex h-14 w-14 items-center justify-center rounded-md border border-slate-200 bg-slate-50 text-xs text-slate-400">
                          N/A
                        </div>
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      {item.prediction === 'Pending' ? (
                        <span className="text-slate-500">Pending</span>
                      ) : (
                        <GradeBadge grade={item.dysplasia_grade} size="sm" />
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      <PredictionBadge prediction={item.prediction} size="sm" />
                    </td>
                    <td className="py-3 pr-4 text-slate-700">
                      {formatDateTime(item.created_at)}
                    </td>
                    <td className="py-3 text-right">
                      <Link to={`/predictions/${item.prediction_id}`}>
                        <Button variant="secondary" size="sm">
                          View result
                        </Button>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
