import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { PredictionOutcome } from '@/api/types'
import { mockFetch, route, type Call } from '@/test/fetchMock'
import { renderAt } from '@/test/render'
import { DashboardPage } from './DashboardPage'
import { PredictPage } from './PredictPage'
import { ResultPage } from './ResultPage'

const OUTCOME: PredictionOutcome = {
  prediction_id: 7,
  prediction: 'Cancer',
  dysplasia_grade: 'moderate',
  assessment: 'inconclusive',
  heatmap_url: 'data:image/png;base64,AA',
  image_url: 'data:image/png;base64,AA',
  pdf_url: '/reports/7',
  created_at: '2026-11-06T10:00:00',
  is_pending_inference: false,
  follow_up: 'needed',
  follow_up_at: '2026-11-06T10:00:00',
  consent_at: '2026-11-06T10:00:00',
  feedback_count: 0,
}

/** The stored record the result page reloads, plus the requests under test. */
const stored = route('GET', '/predictions/7', 200, OUTCOME)

/** Requests other than that reload. */
const writes = (calls: Call[]) => calls.filter((call) => call.method !== 'GET')

function openResult(outcome: PredictionOutcome = OUTCOME) {
  return renderAt(`/predictions/${outcome.prediction_id}`, <ResultPage />, {
    pattern: '/predictions/:id',
    state: { outcome },
    extra: [{ path: '/history', element: <p>History page</p> }],
  })
}

describe('result page', () => {
  it('loads the stored record after an upload, so follow-up and consent show at once', async () => {
    mockFetch(stored)
    // What the upload response carries: no follow-up, consent or version yet.
    openResult({ ...OUTCOME, follow_up: undefined, consent_at: undefined })
    await waitFor(() =>
      expect(screen.getByTestId('follow-up-status')).toHaveTextContent('Follow-up needed'),
    )
    expect(screen.getByText(/Patient consent confirmed/)).toBeInTheDocument()
  })

  it('explains an inconclusive result and marks it as needing follow-up', () => {
    mockFetch(stored)
    openResult()
    expect(screen.getByText(/Not confident enough/)).toBeInTheDocument()
    expect(screen.getByTestId('follow-up-status')).toHaveTextContent('Follow-up needed')
    expect(screen.getByText(/Patient consent confirmed/)).toBeInTheDocument()
  })

  it('records a referral with a note', async () => {
    const user = userEvent.setup()
    const calls = mockFetch(
      stored,
      route('PATCH', '/predictions/7/follow-up', 200, {
        ...OUTCOME,
        follow_up: 'referred',
        follow_up_note: 'Oral medicine, 12 Nov',
      }),
    )
    openResult()
    await user.type(screen.getByLabelText('Note (optional)'), 'Oral medicine, 12 Nov')
    await user.click(screen.getByRole('button', { name: 'Referred' }))
    await waitFor(() =>
      expect(screen.getByTestId('follow-up-status')).toHaveTextContent('Referred'),
    )
    expect(writes(calls)[0].body).toEqual({ status: 'referred', note: 'Oral medicine, 12 Nov' })
  })

  it('needs a reason before sending a wrong-result report', async () => {
    const user = userEvent.setup()
    const calls = mockFetch(stored, route('POST', '/predictions/7/feedback', 201, { id: 1 }))
    openResult()
    await user.click(screen.getByRole('button', { name: 'Send report' }))
    expect(screen.getByText('Choose what was wrong.')).toBeInTheDocument()
    expect(writes(calls)).toHaveLength(0)

    await user.selectOptions(screen.getByLabelText('What was wrong'), 'cancer_result_wrong')
    await user.type(screen.getByLabelText('Actual diagnosis (optional)'), 'Lichen planus')
    await user.click(screen.getByRole('button', { name: 'Send report' }))
    expect(await screen.findByText(/report was saved/)).toBeInTheDocument()
    expect(writes(calls)[0].body).toMatchObject({ kind: 'cancer_result_wrong', actual_diagnosis: 'Lichen planus' })
  })

  it('deletes only after confirmation, then leaves the page', async () => {
    const user = userEvent.setup()
    const calls = mockFetch(stored, route('DELETE', '/predictions/7', 204))
    openResult()
    await user.click(screen.getByRole('button', { name: 'Delete analysis' }))
    expect(writes(calls)).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Yes, delete permanently' }))
    expect(await screen.findByText('History page')).toBeInTheDocument()
    expect(writes(calls)).toEqual([expect.objectContaining({ method: 'DELETE' })])
  })
})

describe('upload page', () => {
  it('will not analyse without the patient consent box ticked', async () => {
    const user = userEvent.setup()
    const calls = mockFetch()
    renderAt('/predict', <PredictPage />)
    await user.click(screen.getByRole('button', { name: /analy/i }))
    expect(
      await screen.findByText('Confirm that the patient has consented before running the analysis.'),
    ).toBeInTheDocument()
    expect(calls.filter((call) => call.url.endsWith('/predict'))).toHaveLength(0)
  })
})

describe('dashboard', () => {
  it('lists results that still need follow-up', async () => {
    mockFetch(
      route('GET', '/predictions', 200, [
        { prediction_id: 1, prediction: 'Cancer', dysplasia_grade: 'severe', assessment: 'cancer',
          created_at: '2026-11-06T10:00:00', follow_up: 'needed' },
        { prediction_id: 2, prediction: 'Cancer', dysplasia_grade: 'mild', assessment: 'cancer',
          created_at: '2026-11-05T10:00:00', follow_up: 'referred' },
        { prediction_id: 3, prediction: 'Non-Cancer', dysplasia_grade: 'none', assessment: 'no_cancer',
          created_at: '2026-11-04T10:00:00', follow_up: null },
      ]),
    )
    renderAt('/', <DashboardPage />)
    const list = await screen.findByTestId('follow-up-list')
    expect(list).toHaveTextContent('Prediction #1')
    expect(list).not.toHaveTextContent('Prediction #2')
    expect(list).not.toHaveTextContent('Prediction #3')
  })
})
