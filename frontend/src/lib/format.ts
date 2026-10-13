/** Display formatting helpers shared by the result page and history table. */

/**
 * 0.96 -> "96%". Model probabilities are never shown as 100% or 0%: rounding
 * 0.998 up to "100%" would present a model output as certainty.
 */
export function formatPercent(value: number): string {
  const pct = Math.round(value * 100)
  if (pct >= 100) return '>99%'
  if (pct <= 0) return '<1%'
  return `${pct}%`
}

export interface ConfidenceBand {
  label: 'Low' | 'Moderate' | 'High'
  description: string
}

/**
 * Plain-language reading of a confidence score.
 *
 * A bare "0.71" invites over-reading. The wording deliberately frames every
 * band as needing clinical review rather than as a verdict.
 */
export function confidenceBand(value: number): ConfidenceBand {
  if (value < 0.7) {
    return {
      label: 'Low',
      description:
        'The model is not confident in this result. Treat it as inconclusive.',
    }
  }

  if (value < 0.85) {
    return {
      label: 'Moderate',
      description:
        'The model leans towards this result but is not certain. Clinical correlation is required.',
    }
  }

  return {
    label: 'High',
    description:
      'The model is confident in this result. Clinical confirmation is still required.',
  }
}

/** ISO timestamp -> "5 Aug 2026, 14:32" in the viewer's locale. */
export function formatDateTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso

  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
