import { useId, type ComponentPropsWithRef } from 'react'

import { cn } from '@/lib/cn'

interface SelectProps extends ComponentPropsWithRef<'select'> {
  label: string
  options: ReadonlyArray<{ value: string; label: string }>
  error?: string
  placeholder?: string
}

export function Select({
  label,
  options,
  error,
  placeholder = 'Select…',
  id,
  className,
  ...props
}: SelectProps) {
  const generatedId = useId()
  const selectId = id ?? generatedId
  const errorId = `${selectId}-error`

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={selectId} className="text-sm font-medium text-slate-700">
        {label}
      </label>
      <select
        id={selectId}
        // Uncontrolled selects start on the placeholder; controlled ones use `value`.
        defaultValue={props.value === undefined ? '' : undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={cn(
          'bg-surface h-10 rounded-md border px-3 text-sm text-slate-900',
          error ? 'border-risk-high' : 'border-surface-border',
          className,
        )}
        {...props}
      >
        <option value="" disabled>
          {placeholder}
        </option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error && (
        <p id={errorId} className="text-risk-high text-xs">
          {error}
        </p>
      )}
    </div>
  )
}
