import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { getPrediction } from '@/api/predictions'
import type { PredictionOutcome } from '@/api/types'
import { DisclaimerBanner } from '@/components/layout/DisclaimerBanner'
import { GradeBadge } from '@/components/result/GradeBadge'
import { ResultScale } from '@/components/result/ResultScale'
import { GRADE_STYLES, RISK_STYLES } from '@/components/result/styles'
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


  // Informational only: it does not change the assessment.
  const sides = outcome.metadata
  const habitSideConcordant =
    (sides?.lesion_side === 'left' || sides?.lesion_side === 'right') &&
    (sides.habit_side === sides.lesion_side || sides.habit_side === 'both')

  // Older analyses have no three-way assessment; derive it from the label.
  const cancerResult =
    outcome.assessment ??
    (outcome.prediction === 'Cancer' ? 'cancer' : outcome.prediction === 'Non-Cancer' ? 'no_cancer' : null)
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
        {!outcome.is_pending_inference && (
          <div className="flex flex-wrap items-center gap-2">
            <GradeBadge grade={outcome.dysplasia_grade} />
            <PredictionBadge
              prediction={outcome.prediction}
              assessment={outcome.assessment}
            />
          </div>
        )}
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
              yet. No result or heatmap is shown, because none exists.
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
            <Card title="Result">
              <dl className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <dt className="text-xs text-slate-500">1. Dysplasia grade</dt>
                  <dd className="flex flex-col gap-1.5">
                    <ResultScale
                      label="Dysplasia grade"
                      selected={outcome.dysplasia_grade}
                      options={[
                        { value: 'none', label: 'None', selectedClass: GRADE_STYLES.none },
                        { value: 'mild', label: 'Mild', selectedClass: GRADE_STYLES.mild },
                        {
                          value: 'moderate',
                          label: 'Moderate',
                          selectedClass: GRADE_STYLES.moderate,
                        },
                        { value: 'severe', label: 'Severe', selectedClass: GRADE_STYLES.severe },
                      ]}
                    />
                    {!outcome.dysplasia_grade && (
                      <span className="text-xs text-slate-500">Grade unavailable</span>
                    )}
                    {outcome.dysplasia_grade && (
                      <span className="text-xs text-slate-500">
                        Low reliability: matched the biopsy grade for about
                        40% of patients in testing.
                      </span>
                    )}
                  </dd>
                </div>
                <div className="flex flex-col gap-1.5">
                  <dt className="text-xs text-slate-500">2. Cancer</dt>
                  <dd className="flex flex-col gap-1.5">
                    <ResultScale
                      label="Cancer"
                      selected={cancerResult}
                      options={[
                        { value: 'cancer', label: 'Cancer', selectedClass: RISK_STYLES.high },
                        ...(outcome.assessment
                          ? [
                              {
                                value: 'inconclusive' as const,
                                label: 'Inconclusive',
                                selectedClass: RISK_STYLES.moderate,
                              },
                            ]
                          : []),
                        { value: 'no_cancer', label: 'No cancer', selectedClass: RISK_STYLES.low },
                      ]}
                    />
                    {cancerResult === 'cancer' && (
                      <span className="text-xs text-slate-500">
                        A screening estimate, not a diagnosis. Please see a
                        dentist or oral medicine specialist for an
                        examination; only a biopsy can confirm cancer.
                      </span>
                    )}
                    {cancerResult === 'inconclusive' && (
                      <span className="text-xs text-slate-500">
                        Not confident enough, across small changes to the photo
                        (angle, light, compression), to rule cancer out. Retake
                        a clear close-up, or refer for examination.
                      </span>
                    )}
                    {outcome.reference_status === 'used' && (
                      <span className="text-xs text-slate-500">
                        Compared with the patient's own opposite-side photo.
                      </span>
                    )}
                    {outcome.reference_status === 'not_normal' && (
                      <span className="text-xs text-slate-500">
                        The opposite-side photo did not look normal either.
                        Examine both sides.
                      </span>
                    )}
                    {habitSideConcordant && (
                      <span className="text-xs text-slate-500">
                        Lesion is on the side where the patient holds pan /
                        tobacco.
                      </span>
                    )}
                    {outcome.reference_image_url && (
                      <AuthorizedImage
                        src={outcome.reference_image_url}
                        alt="Opposite-side reference photo"
                        className="border-surface-border mt-1 h-20 w-20 self-start rounded-md border object-cover"
                      />
                    )}
                  </dd>
                </div>
              </dl>
              <p className="mt-4 text-xs text-slate-500">
                Both are screening estimates from the photo. Grade and
                diagnosis are confirmed only by biopsy.
              </p>
              {outcome.model_version && (
                <p className="mt-2 text-[11px] break-words text-slate-400">
                  Analysis version: {outcome.model_version}
                </p>
              )}
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
