import { useId, type ComponentPropsWithRef } from 'react'

import { cn } from '@/lib/cn'

interface TextareaProps extends ComponentPropsWithRef<'textarea'> {
  label: string
  /** Validation message. Its presence also sets aria-invalid. */
  error?: string
  hint?: string
}

/** Multi-line counterpart of Input, with the same label/hint/error layout. */
export function Textarea({
  label,
  error,
  hint,
  id,
  className,
  rows = 3,
  ...props
}: TextareaProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const errorId = `${inputId}-error`
  const hintId = `${inputId}-hint`

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm font-medium text-slate-700">
        {label}
      </label>
      {hint && (
        <p id={hintId} className="text-xs text-slate-500">
          {hint}
        </p>
      )}
      <textarea
        id={inputId}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={cn(error && errorId, hint && hintId) || undefined}
        className={cn(
          'bg-surface rounded-md border px-3 py-2 text-sm text-slate-900',
          'placeholder:text-slate-400',
          'disabled:cursor-not-allowed disabled:bg-slate-50',
          error ? 'border-risk-high' : 'border-surface-border',
          className,
        )}
        {...props}
      />
      {error && (
        <p id={errorId} className="text-risk-high text-xs">
          {error}
        </p>
      )}
    </div>
  )
}
