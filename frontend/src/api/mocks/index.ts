/**
 * Mock implementations of every planned endpoint.
 *
 * Each function here has the same signature and return type as its real
 * counterpart in ../predictions.ts and ../auth.ts, so the dispatch in those
 * modules is a single `if (USE_MOCKS)` at the top of each function.
 */

import { ApiError } from '../client'
import type {
  AuthResponse,
  FollowUpStatus,
  LoginRequest,
  PatientMetadata,
  PredictionHistoryEntry,
  PredictionOutcome,
  RegisterRequest,
  User,
} from '../types'
import { addRecord, allRecords, findRecord, removeRecord, toHistoryEntry } from './fixtures'

/** Simulate network latency so loading states are actually exercised. */
function delay(minMs = 350, maxMs = 750): Promise<void> {
  const ms = minMs + Math.random() * (maxMs - minMs)
  return new Promise((resolve) => setTimeout(resolve, ms))
}

const MOCK_USER: User = {
  id: 1,
  email: 'clinician@example.org',
  full_name: 'Dr. A. Clinician',
}

export async function login(credentials: LoginRequest): Promise<AuthResponse> {
  await delay()

  if (!credentials.email || !credentials.password) {
    throw new ApiError(400, 'Email and password are required.')
  }

  return {
    access_token: `mock.${btoa(credentials.email)}.token`,
    token_type: 'bearer',
    user: { ...MOCK_USER, email: credentials.email },
  }
}

export async function register(payload: RegisterRequest): Promise<AuthResponse> {
  await delay()

  return {
    access_token: `mock.${btoa(payload.email)}.token`,
    token_type: 'bearer',
    user: {
      ...MOCK_USER,
      email: payload.email,
      full_name: payload.full_name,
    },
  }
}

export async function me(): Promise<User> {
  await delay(100, 250)
  return MOCK_USER
}

export async function uploadPrediction(
  file: File,
  // Accepted so the mock matches the real signature. Mock persistence remains
  // intentionally lightweight and does not model server-side metadata.
  _metadata?: PatientMetadata,
): Promise<PredictionOutcome> {
  // Longer than a normal request: inference is the slow step, and the upload
  // page's progress state needs to be visible for long enough to review.
  await delay(1200, 2000)

  // The object URL is intentionally not revoked -- the record keeps it for the
  // history thumbnail and the result view for the rest of the session.
  return addRecord(file, URL.createObjectURL(file))
}

export async function listPredictions(): Promise<PredictionHistoryEntry[]> {
  await delay()
  return allRecords().map(toHistoryEntry)
}

export async function getPrediction(id: number): Promise<PredictionOutcome> {
  await delay()

  const record = findRecord(id)
  if (!record) {
    throw new ApiError(404, `Prediction ${id} was not found.`)
  }

  return record
}

export async function setFollowUp(
  id: number,
  status: FollowUpStatus,
  note?: string,
): Promise<PredictionOutcome> {
  await delay()
  const record = findRecord(id)
  if (!record) throw new ApiError(404, `Prediction ${id} was not found.`)
  record.follow_up = status
  record.follow_up_note = note ?? null
  record.follow_up_at = new Date().toISOString()
  return record
}

export async function deletePrediction(id: number): Promise<void> {
  await delay()
  removeRecord(id)
}
