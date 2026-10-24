import { cn } from '@/lib/cn'

export interface ScaleOption<T extends string> {
  value: T
  label: string
  /** Classes for the option when it is the model's answer. */
  selectedClass: string
}

interface ResultScaleProps<T extends string> {
  label: string
  options: ScaleOption<T>[]
  selected: T | null | undefined
}

/**
 * Every possible answer side by side, with the model's answer filled in and
 * the rest dimmed -- so a reader sees "Severe" in the context of mild /
 * moderate / severe, not as a lone word.
 */
export function ResultScale<T extends string>({
  label,
  options,
  selected,
}: ResultScaleProps<T>) {
  return (
    <ul aria-label={label} className="flex flex-wrap gap-2">
      {options.map((option) => {
        const isSelected = option.value === selected
        return (
          <li
            key={option.value}
            aria-current={isSelected ? 'true' : undefined}
            className={cn(
              'rounded-full border px-3 py-1 text-sm',
              isSelected
                ? cn('font-semibold', option.selectedClass)
                : 'border-dashed border-slate-200 text-slate-400',
            )}
          >
            {isSelected && <span className="sr-only">Result: </span>}
            {option.label}
          </li>
        )
      })}
    </ul>
  )
}
