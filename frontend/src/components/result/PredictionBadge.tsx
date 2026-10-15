import type { PredictionOutcome } from '@/api/types'
import { cn } from '@/lib/cn'

type Label = PredictionOutcome['prediction']

const STYLES: Record<Label, string> = {
  Cancer: 'border-risk-high-border bg-risk-high-bg text-risk-high',
  'Non-Cancer': 'border-risk-low-border bg-risk-low-bg text-risk-low',
  Pending: 'border-surface-border bg-slate-50 text-slate-500',
}

const LABELS: Record<Label, string> = {
  Cancer: 'Cancer',
  'Non-Cancer': 'No cancer',
  Pending: 'Awaiting inference',
}

interface PredictionBadgeProps {
  prediction: Label
  size?: 'sm' | 'md'
  className?: string
}

export function PredictionBadge({
  prediction,
  size = 'md',
  className,
}: PredictionBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border font-semibold',
        size === 'sm' ? 'px-2.5 py-0.5 text-xs' : 'px-3 py-1 text-sm',
        STYLES[prediction],
        className,
      )}
    >
      {LABELS[prediction]}
    </span>
  )
}
