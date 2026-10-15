import type { DysplasiaGrade } from '@/api/types'

/** Risk colours shared by the result badges and scales (see index.css). */
export const RISK_STYLES = {
  high: 'border-risk-high-border bg-risk-high-bg text-risk-high',
  moderate: 'border-risk-moderate-border bg-risk-moderate-bg text-risk-moderate',
  low: 'border-risk-low-border bg-risk-low-bg text-risk-low',
} as const

export const GRADE_STYLES: Record<DysplasiaGrade, string> = {
  none: RISK_STYLES.low,
  mild: RISK_STYLES.low,
  moderate: RISK_STYLES.moderate,
  severe: RISK_STYLES.high,
}
