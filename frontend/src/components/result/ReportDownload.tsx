import { useState } from 'react'

import { getToken } from '@/api/client'
import { reportUrl } from '@/api/predictions'
import { Button } from '@/components/ui/Button'

interface ReportDownloadProps {
  predictionId: number
  pdfUrl: string | null
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // Not JSON -- fall through to the generic message.
  }
  return `The report could not be generated (HTTP ${response.status}).`
}

export function ReportDownload({ predictionId, pdfUrl }: ReportDownloadProps) {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!pdfUrl) {
    return (
      <Button
        variant="secondary"
        disabled
        title="A report becomes available once the analysis has completed."
        className="w-full"
      >
        Report unavailable
      </Button>
    )
  }

  async function download() {
    setDownloading(true)
    setError(null)
    try {
      // A plain <a href> cannot send the Authorization header the endpoint
      // requires, so fetch the PDF and hand the browser a blob URL instead.
      const response = await fetch(reportUrl(predictionId), {
        headers: { Authorization: `Bearer ${getToken() ?? ''}` },
      })
      if (!response.ok) {
        setError(await readErrorDetail(response))
        return
      }
      const blobUrl = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = blobUrl
      link.download = `oral-lesion-report-${predictionId}.pdf`
      link.click()
      // Revoking synchronously after click() can cancel the download in some
      // browsers before it has started reading the blob.
      setTimeout(() => URL.revokeObjectURL(blobUrl), 30_000)
    } catch {
      setError('Could not reach the server to download the report.')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button onClick={download} loading={downloading} className="w-full">
        Download PDF report
      </Button>
      {error && (
        <p role="alert" className="text-risk-high text-xs">
          {error}
        </p>
      )}
    </div>
  )
}
