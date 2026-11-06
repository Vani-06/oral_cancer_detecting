/**
 * What happens after a result: referral tracking, reporting a wrong result,
 * and deleting the analysis.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { deletePrediction, sendFeedback, setFollowUp } from '@/api/predictions'
import type { FeedbackKind, FollowUpStatus, PredictionOutcome } from '@/api/types'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { formatDateTime } from '@/lib/format'

const FOLLOW_UP_LABELS: Record<FollowUpStatus, string> = {
  needed: 'Follow-up needed',
  referred: 'Referred',
  retake_requested: 'Retake requested',
  closed: 'Closed',
}

const FEEDBACK_OPTIONS: ReadonlyArray<{ value: FeedbackKind; label: string }> = [
  { value: 'cancer_result_wrong', label: 'Cancer result was wrong' },
  { value: 'grade_wrong', label: 'Dysplasia grade was wrong' },
  { value: 'photo_refused_wrongly', label: 'A good photo was refused' },
  { value: 'other', label: 'Something else' },
]

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.detail : 'Something went wrong. Please try again.'
}

export function FollowUpPanel({
  outcome,
  onChange,
}: {
  outcome: PredictionOutcome
  onChange: (next: PredictionOutcome) => void
}) {
  const [note, setNote] = useState(outcome.follow_up_note ?? '')
  const [busy, setBusy] = useState<FollowUpStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function update(status: FollowUpStatus) {
    setBusy(status)
    setError(null)
    try {
      const next = await setFollowUp(outcome.prediction_id, status, note.trim())
      // Keep the locally held image URLs; the server response re-sends them anyway.
      onChange({ ...outcome, ...next, image_url: outcome.image_url ?? next.image_url })
    } catch (cause) {
      setError(errorText(cause))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-700">
        Status:{' '}
        <span className="font-medium" data-testid="follow-up-status">
          {outcome.follow_up ? FOLLOW_UP_LABELS[outcome.follow_up] : 'None recorded'}
        </span>
        {outcome.follow_up_at && (
          <span className="text-slate-500"> · {formatDateTime(outcome.follow_up_at)}</span>
        )}
      </p>
      {outcome.follow_up === 'needed' && (
        <p className="text-xs text-slate-500">
          This result needs an examination or a better photo. Record what was done
          so the patient is not lost to follow-up.
        </p>
      )}
      <Textarea
        label="Note (optional)"
        rows={2}
        maxLength={1000}
        placeholder="e.g. Referred to oral medicine, appointment 12 Nov"
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        {(['referred', 'retake_requested', 'closed'] as const).map((status) => (
          <Button
            key={status}
            size="sm"
            variant={outcome.follow_up === status ? 'primary' : 'secondary'}
            loading={busy === status}
            disabled={busy !== null}
            onClick={() => update(status)}
          >
            {FOLLOW_UP_LABELS[status]}
          </Button>
        ))}
      </div>
      {error && (
        <p role="alert" className="text-risk-high text-sm">
          {error}
        </p>
      )}
    </div>
  )
}

export function FeedbackForm({
  predictionId,
  initialCount = 0,
}: {
  predictionId: number
  initialCount?: number
}) {
  const [kind, setKind] = useState<FeedbackKind | ''>('')
  const [diagnosis, setDiagnosis] = useState('')
  const [comment, setComment] = useState('')
  const [count, setCount] = useState(initialCount)
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (!kind) return setError('Choose what was wrong.')
    setBusy(true)
    setError(null)
    try {
      await sendFeedback(predictionId, {
        kind,
        actual_diagnosis: diagnosis.trim() || undefined,
        comment: comment.trim() || undefined,
      })
      setCount((value) => value + 1)
      setSent(true)
      setKind('')
      setDiagnosis('')
      setComment('')
    } catch (cause) {
      setError(errorText(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-500">
        If the biopsy or your examination disagreed with this result, tell us.
        Reports are reviewed to find where the model fails.
      </p>
      <Select
        label="What was wrong"
        options={FEEDBACK_OPTIONS}
        value={kind}
        onChange={(event) => setKind(event.target.value as FeedbackKind)}
      />
      <Input
        label="Actual diagnosis (optional)"
        maxLength={255}
        placeholder="e.g. Lichen planus on biopsy"
        value={diagnosis}
        onChange={(event) => setDiagnosis(event.target.value)}
      />
      <Textarea
        label="Comment (optional)"
        rows={2}
        maxLength={2000}
        value={comment}
        onChange={(event) => setComment(event.target.value)}
      />
      <Button size="sm" variant="secondary" loading={busy} onClick={submit} className="self-start">
        Send report
      </Button>
      {sent && (
        <p role="status" className="text-sm text-slate-700">
          Thank you, the report was saved.
        </p>
      )}
      {count > 0 && (
        <p className="text-xs text-slate-500">
          {count} report{count === 1 ? '' : 's'} filed on this analysis.
        </p>
      )}
      {error && (
        <p role="alert" className="text-risk-high text-sm">
          {error}
        </p>
      )}
    </div>
  )
}

export function DeleteAnalysis({ predictionId }: { predictionId: number }) {
  const navigate = useNavigate()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      await deletePrediction(predictionId)
      navigate('/history', { replace: true })
    } catch (cause) {
      setError(errorText(cause))
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-500">
        Deletes this analysis permanently, with its photos, heatmap and report.
        This cannot be undone.
      </p>
      {confirming ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="danger" loading={busy} onClick={remove}>
            Yes, delete permanently
          </Button>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => setConfirming(false)}>
            Cancel
          </Button>
        </div>
      ) : (
        <Button size="sm" variant="secondary" className="self-start" onClick={() => setConfirming(true)}>
          Delete analysis
        </Button>
      )}
      {error && (
        <p role="alert" className="text-risk-high text-sm">
          {error}
        </p>
      )}
    </div>
  )
}
