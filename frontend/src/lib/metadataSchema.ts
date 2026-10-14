import { z } from 'zod'

import type { PatientMetadata } from '@/api/types'

/**
 * Patient metadata form schema -- the second modality.
 *
 * Field names match the PatientMetadata contract in src/api/types.ts exactly,
 * and the assertion at the bottom of this file fails the build if they ever
 * drift apart. The validated object is sent as metadata_json with the image.
 */

export const SEX_OPTIONS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
] as const

export const TOBACCO_TYPE_OPTIONS = [
  { value: 'smoked', label: 'Smoked (cigarette, bidi, cigar)' },
  { value: 'smokeless', label: 'Smokeless (chewing, snuff, gutkha)' },
  { value: 'both', label: 'Both' },
] as const

export const LESION_SITE_OPTIONS = [
  { value: 'buccal_mucosa', label: 'Buccal mucosa' },
  { value: 'tongue', label: 'Tongue' },
  { value: 'gingiva', label: 'Gingiva' },
  { value: 'palate', label: 'Palate' },
  { value: 'floor_of_mouth', label: 'Floor of mouth' },
  { value: 'lip', label: 'Lip' },
  { value: 'retromolar_trigone', label: 'Retromolar trigone' },
  { value: 'alveolar_ridge', label: 'Alveolar ridge' },
  { value: 'other', label: 'Other (describe in clinical notes)' },
] as const

const LESION_SITES = [
  'buccal_mucosa',
  'tongue',
  'gingiva',
  'palate',
  'floor_of_mouth',
  'lip',
  'retromolar_trigone',
  'alveolar_ridge',
  'other',
] as const

/** Optional free text. The form maps blank input to undefined (textField). */
function optionalText(max: number) {
  return z.string().max(max, `Enter ${max} characters or fewer`).optional()
}

const YES_NO_REQUIRED = 'Select yes or no'

export const patientMetadataSchema = z
  .object({
    patient_reference: optionalText(64),
    age: z
      .number({ error: 'Enter the patient age' })
      .int('Age must be a whole number')
      .min(1, 'Age must be at least 1')
      .max(120, 'Age must be 120 or below'),
    sex: z.enum(['male', 'female', 'other'], {
      error: 'Select the patient sex',
    }),

    tobacco_use: z.boolean({ error: YES_NO_REQUIRED }),
    tobacco_type: z.enum(['smoked', 'smokeless', 'both']).optional(),
    tobacco_years: z
      .number()
      .int('Enter a whole number of years')
      .min(0, 'Years cannot be negative')
      .max(100, 'Enter 100 years or fewer')
      .optional(),

    betel_quid_use: z.boolean({ error: YES_NO_REQUIRED }),
    betel_quid_years: z
      .number()
      .int('Enter a whole number of years')
      .min(0, 'Years cannot be negative')
      .max(100, 'Enter 100 years or fewer')
      .optional(),
    alcohol_use: z.boolean({ error: YES_NO_REQUIRED }),

    lesion_site: z.enum(LESION_SITES, { error: 'Select the lesion site' }),
    // Optional: often not known, and the client's case sheet rarely has it.
    lesion_duration_weeks: z
      .number()
      .int('Enter a whole number of weeks')
      .min(0, 'Duration cannot be negative')
      .max(520, 'Enter 520 weeks (10 years) or fewer')
      .optional(),

    pain: z.boolean({ error: YES_NO_REQUIRED }),
    bleeding: z.boolean({ error: YES_NO_REQUIRED }),
    prior_lesion_history: z.boolean({ error: YES_NO_REQUIRED }),

    medical_history: optionalText(1000),
    clinical_notes: optionalText(2000),
  })
  // The tobacco follow-ups are only meaningful, and only required, when the
  // patient uses tobacco.
  .superRefine((values, ctx) => {
    if (!values.tobacco_use) return

    if (!values.tobacco_type) {
      ctx.addIssue({
        code: 'custom',
        path: ['tobacco_type'],
        message: 'Select the type of tobacco used',
      })
    }

    if (values.tobacco_years === undefined) {
      ctx.addIssue({
        code: 'custom',
        path: ['tobacco_years'],
        message: 'Enter the number of years of use',
      })
    }
  })

export type PatientMetadataValues = z.infer<typeof patientMetadataSchema>

/**
 * Compile-time guarantee that the form produces exactly what the API expects.
 * If a field is renamed here but not in PatientMetadata (or vice versa), this
 * resolves to `false` and `tsc` fails.
 */
type Expect<T extends true> = T
export type MetadataMatchesApiContract = Expect<
  PatientMetadataValues extends PatientMetadata ? true : false
>

/** Human-readable labels, for rendering a submitted record back to the user. */
export const METADATA_FIELD_LABELS: Record<keyof PatientMetadataValues, string> =
  {
    patient_reference: 'Patient ID',
    age: 'Age',
    sex: 'Sex',
    tobacco_use: 'Tobacco use',
    tobacco_type: 'Tobacco type',
    tobacco_years: 'Years of tobacco use',
    betel_quid_use: 'Betel quid / areca nut',
    betel_quid_years: 'Years of betel quid use',
    alcohol_use: 'Alcohol use',
    lesion_site: 'Lesion site',
    lesion_duration_weeks: 'Lesion duration',
    pain: 'Pain',
    bleeding: 'Bleeding',
    prior_lesion_history: 'Prior oral lesion',
    medical_history: 'Medical history',
    clinical_notes: 'Clinical notes',
  }

function labelFrom(
  options: ReadonlyArray<{ value: string; label: string }>,
  value: string,
): string {
  return options.find((option) => option.value === value)?.label ?? value
}

/** Format one metadata value for display. */
export function formatMetadataValue(
  key: keyof PatientMetadataValues,
  value: PatientMetadataValues[keyof PatientMetadataValues],
): string {
  if (value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'

  switch (key) {
    case 'age':
      return `${value} years`
    case 'lesion_duration_weeks':
      return `${value} ${value === 1 ? 'week' : 'weeks'}`
    case 'tobacco_years':
    case 'betel_quid_years':
      return `${value} ${value === 1 ? 'year' : 'years'}`
    case 'sex':
      return labelFrom(SEX_OPTIONS, String(value))
    case 'tobacco_type':
      return labelFrom(TOBACCO_TYPE_OPTIONS, String(value))
    case 'lesion_site':
      return labelFrom(LESION_SITE_OPTIONS, String(value))
    default:
      return String(value)
  }
}
