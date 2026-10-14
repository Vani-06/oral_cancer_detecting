import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { getPrediction } from '@/api/predictions'
import type { PredictionOutcome } from '@/api/types'
import { DisclaimerBanner } from '@/components/layout/DisclaimerBanner'
import { ConfidenceGauge } from '@/components/result/ConfidenceGauge'
import { HeatmapViewer } from '@/components/result/HeatmapViewer'
import { MetadataSummary } from '@/components/result/MetadataSummary'
import { PredictionBadge } from '@/components/result/PredictionBadge'
import { ReportDownload } from '@/components/result/ReportDownload'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'
import { formatDateTime } from '@/lib/format'
import type { PatientMetadataValues } from '@/lib/metadataSchema'
import { AuthorizedImage } from '@/components/ui/AuthorizedImage'

interface ResultLocationState {
  outcome?: PredictionOutcome
  metadata?: PatientMetadataValues
}

export function ResultPage() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const { outcome, metadata } =
    (location.state as ResultLocationState | null) ?? {}

  // Keyed on the id: react-router reuses one component instance across param
  // changes, so without this a stale result (or a stale error) would survive a
  // move from one prediction to another.
  return (
    <ResultView
      key={id}
      predictionId={Number(id)}
      providedOutcome={outcome}
      metadata={metadata}
    />
  )
}

interface ResultViewProps {
  predictionId: number
  providedOutcome?: PredictionOutcome
  metadata?: PatientMetadataValues
}

function ResultView({
  predictionId,
  providedOutcome,
  metadata,
}: ResultViewProps) {
  const [outcome, setOutcome] = useState<PredictionOutcome | null>(
    providedOutcome ?? null,
  )
  const [loading, setLoading] = useState(!providedOutcome)
  const [error, setError] = useState<string | null>(null)

  // Only fetch when the prediction did not arrive with the navigation, i.e. on
  // a deep link or a reload.
  useEffect(() => {
    if (providedOutcome) return

    let cancelled = false

    getPrediction(predictionId)
      .then((result) => {
        if (!cancelled) setOutcome(result)
      })
      .catch((cause: unknown) => {
        if (cancelled) return
        setError(
          cause instanceof ApiError
            ? cause.detail
            : 'This prediction could not be loaded.',
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [predictionId, providedOutcome])

  if (loading) {
    return (
      <div className="flex min-h-64 items-center justify-center">
        <Spinner className="text-brand-600 h-8 w-8" label="Loading prediction" />
      </div>
    )
  }

  if (error || !outcome) {
    return (
      <div className="mx-auto flex max-w-lg flex-col items-center gap-4 py-12 text-center">
        <h1 className="text-xl font-semibold text-slate-900">
          Prediction unavailable
        </h1>
        <p className="text-sm text-slate-600">
          {error ?? 'This prediction could not be loaded.'}
        </p>
        <div className="flex gap-3">
          <Link to="/history">
            <Button variant="secondary">Back to history</Button>
          </Link>
          <Link to="/predict">
            <Button>New analysis</Button>
          </Link>
        </div>
      </div>
    )
  }

  // Navigation state carries the form values right after an upload; on a
  // reload or when opened from history, the server's stored copy is used.
  const patientContext = metadata ?? outcome.metadata ?? undefined

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">
            Analysis result
          </h1>
          <p className="text-sm text-slate-600">
            {formatDateTime(outcome.created_at)}
            {outcome.filename && (
              <span className="text-slate-400"> · {outcome.filename}</span>
            )}
          </p>
        </div>
        <PredictionBadge prediction={outcome.prediction} />
      </div>

      <DisclaimerBanner className="rounded-md border" />

      {outcome.is_pending_inference ? (
        <Card title="Awaiting inference">
          <div className="flex flex-col gap-4">
            <p className="text-sm text-slate-600">
              The image was uploaded and stored on the server, but no prediction
              was produced: there is no model behind{' '}
              <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">
                POST /predict
              </code>{' '}
              yet. No confidence score or heatmap is shown, because none exists.
            </p>
            {outcome.image_url && (
              <AuthorizedImage
                src={outcome.image_url}
                alt="Uploaded oral lesion"
                className="border-surface-border max-h-72 self-start rounded-md border object-contain"
              />
            )}
          </div>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3 lg:items-start">
          <Card title="Explainability" className="lg:col-span-2">
            <HeatmapViewer
              imageUrl={outcome.image_url}
              heatmapUrl={outcome.heatmap_url}
            />
          </Card>

          <div className="flex flex-col gap-6">
            <Card title="Confidence">
              <ConfidenceGauge
                value={outcome.confidence}
                prediction={outcome.prediction}
              />
            </Card>

            <Card title="Report">
              <ReportDownload
                predictionId={outcome.prediction_id}
                pdfUrl={outcome.pdf_url}
              />
            </Card>
          </div>
        </div>
      )}

      <Card title="Patient context">
        {patientContext ? (
          <MetadataSummary metadata={patientContext} />
        ) : (
          <p className="text-sm text-slate-600">
            No patient metadata was recorded with this analysis.
          </p>
        )}
      </Card>
    </div>
  )
}
