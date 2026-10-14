import type { DysplasiaGrade } from '@/api/types'
import { cn } from '@/lib/cn'

const STYLES: Record<DysplasiaGrade, string> = {
  mild: 'border-risk-low-border bg-risk-low-bg text-risk-low',
  moderate: 'border-risk-moderate-border bg-risk-moderate-bg text-risk-moderate',
  severe: 'border-risk-high-border bg-risk-high-bg text-risk-high',
}

const LABELS: Record<DysplasiaGrade, string> = {
  mild: 'Mild dysplasia',
  moderate: 'Moderate dysplasia',
  severe: 'Severe dysplasia',
}

interface GradeBadgeProps {
  grade: DysplasiaGrade | null | undefined
  size?: 'sm' | 'md'
  className?: string
}

/** The predicted dysplasia grade. No grade (no grading model, or still
 *  pending) is shown as such rather than hidden. */
export function GradeBadge({ grade, size = 'md', className }: GradeBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border font-semibold',
        size === 'sm' ? 'px-2.5 py-0.5 text-xs' : 'px-3 py-1 text-sm',
        grade ? STYLES[grade] : 'border-surface-border bg-slate-50 text-slate-500',
        className,
      )}
    >
      {grade ? LABELS[grade] : 'Grade unavailable'}
    </span>
  )
}
