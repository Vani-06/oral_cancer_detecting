/**
 * Wire types.
 *
 * These mirror backend/app/schemas/prediction.py field-for-field, snake_case
 * included. Do not rename fields on the client -- keeping the names identical
 * means a single grep finds every producer and consumer across both languages.
 */

/** Class labels the model can emit. The backend types this as a plain `str`. */
export type PredictionLabel = 'Cancer' | 'Non-Cancer'

/** Predicted grade of epithelial dysplasia; null when no grading model ran. */
export type DysplasiaGrade = 'none' | 'mild' | 'moderate' | 'severe'

/**
 * Final call. 'inconclusive' means the answer was not stable under edits
 * that should not change it (mirror, rotation, lighting, compression) --
 * retake the photo or refer.
 */
export type Assessment = 'cancer' | 'no_cancer' | 'inconclusive'

/**
 * Same-patient opposite-side reference: 'used', or 'not_normal' when that
 * photo itself looked abnormal and the lesion photo was assessed alone.
 * null when no reference photo was given.
 */
export type ReferenceStatus = 'used' | 'not_normal'

/** Mirrors `PredictionUploadResponse`. What POST /predict returns today. */
export interface PredictionUploadResponse {
  prediction_id: number
  filename: string
  status: string
  message: string
  created_at: string
  image_url: string | null
  reference_image_url?: string | null
  prediction: PredictionLabel | 'Pending'
  dysplasia_grade: DysplasiaGrade | null
  assessment?: Assessment | null
  reference_status?: ReferenceStatus | null
  heatmap_url: string | null
  pdf_url: string | null
  is_pending_inference: boolean
}

/** Mirrors `PredictionResult`. What POST /predict will return post-inference. */
export interface PredictionResult {
  prediction_id: number
  prediction: PredictionLabel
  dysplasia_grade: DysplasiaGrade | null
  assessment?: Assessment | null
  reference_status?: ReferenceStatus | null
  heatmap_url: string | null
  pdf_url: string | null
}

/** Mirrors `PredictionHistoryItem`. One row of GET /predictions. */
export interface PredictionHistoryItem {
  prediction_id: number
  prediction: PredictionLabel | 'Pending'
  dysplasia_grade: DysplasiaGrade | null
  assessment?: Assessment | null
  reference_status?: ReferenceStatus | null
  created_at: string
  image_url?: string | null
}

/**
 * Client-side view of a prediction.
 *
 * Extends the wire model with fields the UI needs but the API does not send:
 * a thumbnail to render, and an explicit pending flag. `is_pending_inference`
 * is set when the live backend accepted the image but has no model behind it
 * yet -- the result page must say exactly that instead of showing a number.
 */
export interface PredictionOutcome extends Omit<PredictionResult, 'prediction'> {
  prediction: PredictionLabel | 'Pending'
  is_pending_inference: boolean
  created_at: string
  /** Server-side filename returned by the upload endpoint, when known. */
  filename?: string
  /** Object URL or data URI for the source image, for previews and thumbnails. */
  image_url?: string
  /** The same patient's opposite-side photo, when one was taken. */
  reference_image_url?: string | null
  /** Patient metadata stored with the prediction (GET /predictions/{id}). */
  metadata?: PatientMetadata | null
  /** Models and thresholds that produced this result. */
  model_version?: string | null
}

/** A history row plus the extras the table renders. */
export interface PredictionHistoryEntry extends PredictionHistoryItem {
  image_url?: string | null
}

/**
 * Structured patient metadata -- the second modality.
 *
 * Defined here rather than derived from the Phase 3 zod schema so that the
 * schema can be checked against the API contract instead of silently becoming
 * it. The form's `z.infer` type must satisfy this interface.
 *
 * Sent as the `metadata_json` multipart field with the image upload.
 */
export interface PatientMetadata {
  patient_reference?: string
  age: number
  sex: 'male' | 'female' | 'other'
  tobacco_use: boolean
  tobacco_type?: 'smoked' | 'smokeless' | 'both'
  tobacco_years?: number
  betel_quid_use: boolean
  betel_quid_years?: number
  alcohol_use: boolean
  lesion_side?: 'left' | 'right' | 'midline'
  habit_side?: 'left' | 'right' | 'both'
  lesion_site:
    | 'buccal_mucosa'
    | 'tongue'
    | 'gingiva'
    | 'palate'
    | 'floor_of_mouth'
    | 'lip'
    | 'retromolar_trigone'
    | 'alveolar_ridge'
    | 'other'
  lesion_duration_weeks?: number
  pain: boolean
  bleeding: boolean
  prior_lesion_history: boolean
  medical_history?: string
  clinical_notes?: string
}

/** Authenticated user, from GET /me. */
export interface User {
  id: number
  email: string
  full_name: string
}

/** What POST /login and POST /register return. */
export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest extends LoginRequest {
  full_name: string
  /** Must be true: a health professional with the patient's consent. */
  confirms_professional_use: true
}
