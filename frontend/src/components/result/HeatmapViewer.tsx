import { useId, useState } from 'react'

import { resolveUrl } from '@/api/client'
import { useAuthorizedImage } from '@/hooks/useAuthorizedImage'
import { cn } from '@/lib/cn'

type Mode = 'overlay' | 'side-by-side'

interface HeatmapViewerProps {
  imageUrl?: string
  /** Grad-CAM overlay. Server-relative paths are resolved against the API. */
  heatmapUrl: string | null
  alt?: string
}

export function HeatmapViewer({
  imageUrl,
  heatmapUrl,
  alt = 'Analysed oral lesion',
}: HeatmapViewerProps) {
  const sliderId = useId()
  const [mode, setMode] = useState<Mode>('overlay')
  const [opacity, setOpacity] = useState(0.6)
  // Both are owner-only API resources, fetched with the auth token.
  const source = useAuthorizedImage(imageUrl ? resolveUrl(imageUrl) : null)
  const overlay = useAuthorizedImage(heatmapUrl ? resolveUrl(heatmapUrl) : null)

  if (!imageUrl) {
    return (
      <p className="text-sm text-slate-600">
        The source image is not available for this prediction. Images are held
        for the current session only.
      </p>
    )
  }

  if (!source) {
    return <p className="text-sm text-slate-600">Loading image…</p>
  }

  if (!heatmapUrl) {
    return (
      <div className="flex flex-col gap-3">
        <img
          src={source}
          alt={alt}
          className="border-surface-border w-full rounded-md border object-contain"
        />
        <p className="text-xs text-slate-500">
          No explainability heatmap is available for this prediction.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          className="border-surface-border inline-flex rounded-md border p-0.5"
          role="group"
          aria-label="Heatmap display mode"
        >
          {(
            [
              ['overlay', 'Overlay'],
              ['side-by-side', 'Side by side'],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={mode === value}
              onClick={() => setMode(value)}
              className={cn(
                'rounded px-3 py-1 text-xs font-medium transition-colors',
                mode === value
                  ? 'bg-brand-600 text-white'
                  : 'text-slate-600 hover:bg-slate-100',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === 'overlay' && (
          <div className="flex items-center gap-2">
            <label htmlFor={sliderId} className="text-xs text-slate-600">
              Heatmap opacity
            </label>
            <input
              id={sliderId}
              type="range"
              min={0}
              max={100}
              step={5}
              value={Math.round(opacity * 100)}
              aria-valuetext={`${Math.round(opacity * 100)} percent`}
              onChange={(event) =>
                setOpacity(Number(event.target.value) / 100)
              }
              className="accent-brand-600 w-32"
            />
            <span className="w-9 text-right text-xs tabular-nums text-slate-500">
              {Math.round(opacity * 100)}%
            </span>
          </div>
        )}
      </div>

      {mode === 'overlay' ? (
        <div className="border-surface-border relative overflow-hidden rounded-md border">
          <img src={source} alt={alt} className="w-full object-contain" />
          <img
            src={overlay}
            alt=""
            aria-hidden="true"
            style={{ opacity }}
            className="pointer-events-none absolute inset-0 h-full w-full object-contain"
          />
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <figure className="flex flex-col gap-1">
            <img
              src={source}
              alt={alt}
              className="border-surface-border w-full rounded-md border object-contain"
            />
            <figcaption className="text-xs text-slate-500">Original</figcaption>
          </figure>
          <figure className="flex flex-col gap-1">
            <div className="border-surface-border relative overflow-hidden rounded-md border">
              <img src={source} alt="" aria-hidden="true" className="w-full object-contain" />
              <img
                src={overlay}
                alt={`Grad-CAM heatmap for ${alt}`}
                className="absolute inset-0 h-full w-full object-contain"
              />
            </div>
            <figcaption className="text-xs text-slate-500">
              Grad-CAM heatmap
            </figcaption>
          </figure>
        </div>
      )}

      <p className="text-xs text-slate-500">
        Warmer regions indicate areas that most influenced the model's output.
        They mark where the model looked, not a clinical margin.
      </p>
    </div>
  )
}
