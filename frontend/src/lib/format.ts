/** Display formatting helpers shared by the result, history and dashboard pages. */

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
