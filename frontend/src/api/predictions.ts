/**
 * Prediction endpoints.
 *
 * The backend stores relative asset URLs. Normalize them at this boundary so
 * every page works when the API and frontend are deployed separately.
 */

import { getJson, postForm, resolveUrl, USE_MOCKS } from './client'
import * as mocks from './mocks'
import type {
  PatientMetadata,
  PredictionHistoryEntry,
  PredictionOutcome,
  PredictionUploadResponse,
} from './types'

/**
 * Metadata is sent as one JSON form field to keep the multipart contract
 * stable as the metadata schema grows.
 */
const SEND_METADATA: boolean = true

function normalizeOutcome(outcome: PredictionOutcome): PredictionOutcome {
  return {
    ...outcome,
    image_url: outcome.image_url ? resolveUrl(outcome.image_url) : outcome.image_url,
    heatmap_url: outcome.heatmap_url
      ? resolveUrl(outcome.heatmap_url)
      : outcome.heatmap_url,
    reference_image_url: outcome.reference_image_url
      ? resolveUrl(outcome.reference_image_url)
      : outcome.reference_image_url,
    pdf_url: outcome.pdf_url ? resolveUrl(outcome.pdf_url) : outcome.pdf_url,
  }
}

export async function uploadPrediction(
  file: File,
  metadata?: PatientMetadata,
  referenceFile?: File | null,
): Promise<PredictionOutcome> {
  if (USE_MOCKS) return mocks.uploadPrediction(file, metadata)

  const form = new FormData()
  form.append('file', file)
  if (referenceFile) form.append('reference_file', referenceFile)

  if (SEND_METADATA && metadata) {
    form.append('metadata_json', JSON.stringify(metadata))
  }

  const response = await postForm<PredictionUploadResponse>('/predict', form)

  return normalizeOutcome({
    prediction_id: response.prediction_id,
    prediction: response.prediction,
    dysplasia_grade: response.dysplasia_grade,
    assessment: response.assessment,
    reference_status: response.reference_status,
    reference_image_url: response.reference_image_url ?? null,
    heatmap_url: response.heatmap_url,
    pdf_url: response.pdf_url,
    created_at: response.created_at,
    filename: response.filename,
    image_url: response.image_url ?? URL.createObjectURL(file),
    is_pending_inference: response.is_pending_inference,
  })
}

export function listPredictions(): Promise<PredictionHistoryEntry[]> {
  if (USE_MOCKS) return mocks.listPredictions()
  return getJson<PredictionHistoryEntry[]>('/predictions').then((items) =>
    items.map((item) => ({
      ...item,
      image_url: item.image_url ? resolveUrl(item.image_url) : item.image_url,
    })),
  )
}

export function getPrediction(id: number): Promise<PredictionOutcome> {
  if (USE_MOCKS) return mocks.getPrediction(id)
  return getJson<PredictionOutcome>(`/predictions/${id}`).then(normalizeOutcome)
}

/** Absolute URL of the generated PDF report, for a download link. */
export function reportUrl(predictionId: number): string {
  return resolveUrl(`/reports/${predictionId}`)
}
