import {
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from 'react'

import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/cn'
import {
  ACCEPT_ATTRIBUTE,
  ALLOWED_EXTENSIONS,
  MAX_FILE_SIZE_MB,
  formatFileSize,
  validateImageFile,
} from '@/lib/imageValidation'

interface ImageDropzoneProps {
  file: File | null
  onFileChange: (file: File | null) => void
  /** Error owned by the parent, e.g. "an image is required" on submit. */
  error?: string | null
  disabled?: boolean
  /** Call to action shown in the empty drop area. */
  prompt?: string
}

export function ImageDropzone({
  file,
  onFileChange,
  error,
  disabled = false,
  prompt = 'Drop a lesion image here, or click to browse',
}: ImageDropzoneProps) {
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const previewRef = useRef<string | null>(null)

  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  // Release the last object URL when the component goes away. Object URLs are
  // held by the document until revoked, so a long session of uploads would
  // otherwise pin every previewed image in memory.
  useEffect(() => {
    return () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    }
  }, [])

  function setPreview(next: File | null) {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current)
    const url = next ? URL.createObjectURL(next) : null
    previewRef.current = url
    setPreviewUrl(url)
  }

  function select(next: File | null) {
    if (!next) {
      setLocalError(null)
      setPreview(null)
      onFileChange(null)
      return
    }

    const message = validateImageFile(next)
    if (message) {
      setLocalError(message)
      setPreview(null)
      onFileChange(null)
      return
    }

    setLocalError(null)
    setPreview(next)
    onFileChange(next)
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    select(event.target.files?.[0] ?? null)
    // Allows re-selecting the same file after removing it.
    event.target.value = ''
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault()
    setDragActive(false)
    if (disabled) return
    select(event.dataTransfer.files?.[0] ?? null)
  }

  function handleDragOver(event: DragEvent<HTMLElement>) {
    event.preventDefault()
    if (!disabled) setDragActive(true)
  }

  const shownError = localError ?? error ?? null
  const errorId = `${inputId}-error`

  return (
    <div className="flex flex-col gap-3">
      {/* A real file input kept in the accessibility tree: the label below is
          its control, so click, Enter and Space all work without extra JS. */}
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={ACCEPT_ATTRIBUTE}
        disabled={disabled}
        onChange={handleInputChange}
        className="peer sr-only"
        aria-describedby={shownError ? errorId : undefined}
        aria-invalid={shownError ? true : undefined}
      />

      <label
        htmlFor={inputId}
        onDragOver={handleDragOver}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        className={cn(
          'flex min-h-56 flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-6 text-center transition-colors',
          'peer-focus-visible:outline-brand-600 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2',
          disabled
            ? 'cursor-not-allowed border-slate-200 bg-slate-50'
            : 'cursor-pointer',
          dragActive && !disabled && 'border-brand-500 bg-brand-50',
          !dragActive &&
            !disabled &&
            (shownError
              ? 'border-risk-high-border bg-risk-high-bg'
              : 'border-surface-border bg-surface hover:bg-slate-50'),
        )}
      >
        {previewUrl ? (
          <img
            src={previewUrl}
            alt={`Selected lesion image: ${file?.name ?? ''}`}
            className="max-h-48 rounded-md object-contain"
          />
        ) : (
          <>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              className="h-10 w-10 text-slate-400"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 16.5V18a3 3 0 0 0 3 3h12a3 3 0 0 0 3-3v-1.5M12 3v13.5M12 3 7.5 7.5M12 3l4.5 4.5"
              />
            </svg>
            <span className="text-sm font-medium text-slate-700">
              {prompt}
            </span>
            <span className="text-xs text-slate-500">
              {ALLOWED_EXTENSIONS.join(', ')} · up to {MAX_FILE_SIZE_MB} MB
            </span>
          </>
        )}
      </label>

      {file && (
        <div className="border-surface-border bg-surface flex items-center justify-between gap-3 rounded-md border px-3 py-2">
          <span className="min-w-0 truncate text-sm text-slate-700">
            {file.name}
            <span className="text-slate-400"> · {formatFileSize(file.size)}</span>
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={disabled}
            onClick={() => select(null)}
          >
            Remove
          </Button>
        </div>
      )}

      {shownError && (
        <p id={errorId} role="alert" className="text-risk-high text-sm">
          {shownError}
        </p>
      )}
    </div>
  )
}
