import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { uploadPrediction } from '@/api/predictions'
import { PatientMetadataForm } from '@/components/metadata/PatientMetadataForm'
import { Card } from '@/components/ui/Card'
import { ImageDropzone } from '@/components/upload/ImageDropzone'
import type { PatientMetadataValues } from '@/lib/metadataSchema'

export function PredictPage() {
  const navigate = useNavigate()

  const [file, setFile] = useState<File | null>(null)
  const [referenceFile, setReferenceFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [consent, setConsent] = useState(false)
  const [consentError, setConsentError] = useState(false)

  const MISSING_IMAGE = 'Select a lesion image before running the analysis.'

  /** Runs when the metadata form itself is invalid, so both problems show at once. */
  function handleInvalid() {
    setFileError(file ? null : MISSING_IMAGE)
    setConsentError(!consent)
  }

  async function handleAnalyse(metadata: PatientMetadataValues) {
    if (!file || !consent) {
      setFileError(file ? null : MISSING_IMAGE)
      setConsentError(!consent)
      return
    }

    setFileError(null)
    setUploadError(null)
    setSubmitting(true)

    try {
      // Metadata is sent with the image and also carried through navigation so
      // the result is immediately useful before a reload.
      const outcome = await uploadPrediction(file, metadata, referenceFile, consent)
      navigate(`/predictions/${outcome.prediction_id}`, {
        state: { outcome, metadata },
      })
    } catch (error) {
      setUploadError(
        error instanceof ApiError
          ? error.detail
          : 'The image could not be uploaded. Please try again.',
      )
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">New analysis</h1>
        <p className="text-sm text-slate-600">
          Upload an oral lesion image and record the patient context. Adding a
          photo of the same site on the patient's healthy opposite side lets the
          analysis compare the lesion with their own normal tissue.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
        <div className="flex flex-col gap-6">
          <Card title="Lesion image">
            <ImageDropzone
              file={file}
              onFileChange={(next) => {
                setFile(next)
                if (next) setFileError(null)
              }}
              error={fileError}
              disabled={submitting}
            />
          </Card>

          <Card title="Opposite side (optional)">
            <div className="flex flex-col gap-3">
              <p className="text-sm text-slate-600">
                Photograph the matching site on the other side of the mouth --
                for a left cheek lesion, the healthy right cheek. Use the same
                phone, light and distance as the lesion photo.
              </p>
              <ImageDropzone
                file={referenceFile}
                onFileChange={setReferenceFile}
                disabled={submitting}
                prompt="Drop the opposite-side photo here, or click to browse"
              />
            </div>
          </Card>
        </div>

        <Card title="Patient metadata">
          <PatientMetadataForm
            onSubmit={handleAnalyse}
            onInvalid={handleInvalid}
            submitting={submitting}
            footer={
              <div className="flex flex-col gap-3">
                <label className="flex items-start gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4"
                    checked={consent}
                    disabled={submitting}
                    onChange={(event) => {
                      setConsent(event.target.checked)
                      if (event.target.checked) setConsentError(false)
                    }}
                  />
                  <span>
                    The patient has consented to these photos being uploaded and
                    analysed.
                  </span>
                </label>
                {consentError && (
                  <p role="alert" className="text-risk-high text-sm">
                    Confirm that the patient has consented before running the analysis.
                  </p>
                )}
                {fileError && (
                  <p
                    role="alert"
                    className="border-risk-high-border bg-risk-high-bg text-risk-high rounded-md border px-3 py-2 text-sm"
                  >
                    {fileError}
                  </p>
                )}
                {uploadError && (
                  <p
                    role="alert"
                    className="border-risk-high-border bg-risk-high-bg text-risk-high rounded-md border px-3 py-2 text-sm"
                  >
                    {uploadError}
                  </p>
                )}
                <p className="text-xs text-slate-500">
                  Patient details are recorded for the report and the clinical record. They do not change the analysis result.
                </p>
              </div>
            }
          />
        </Card>
      </div>
    </div>
  )
}
