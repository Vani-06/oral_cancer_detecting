/**
 * Fixture data for mock mode.
 *
 * Everything here is deterministic given its seed, so the same image uploaded
 * twice yields the same prediction and the same heatmap. That matters for demos
 * -- a result that changes on every refresh looks broken.
 */

import type {
  DysplasiaGrade,
  PredictionLabel,
  PredictionOutcome,
  PredictionHistoryEntry,
} from '../types'

/** mulberry32 -- small, fast, good enough for reproducible fixtures. */
function seededRandom(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** FNV-1a. Turns a filename into a stable seed. */
function hashString(value: string): number {
  let hash = 2166136261
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function svgDataUri(svg: string): string {
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

/**
 * Stand-in for a clinical photograph, used as a history thumbnail.
 * Mucosa-toned so the table reads plausibly without shipping real patient data.
 */
export function mockThumbnail(seed: number): string {
  const rand = seededRandom(seed)
  const hue = 340 + rand() * 20
  const lesionX = 30 + rand() * 40
  const lesionY = 30 + rand() * 40
  const lesionR = 10 + rand() * 12

  return svgDataUri(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">` +
      `<defs><radialGradient id="l"><stop offset="0%" stop-color="hsl(${hue.toFixed(0)} 45% 82%)"/>` +
      `<stop offset="100%" stop-color="hsl(${hue.toFixed(0)} 40% 62%)"/></radialGradient></defs>` +
      `<rect width="100" height="100" fill="hsl(${hue.toFixed(0)} 38% 55%)"/>` +
      `<ellipse cx="${lesionX.toFixed(1)}" cy="${lesionY.toFixed(1)}" rx="${lesionR.toFixed(1)}" ry="${(lesionR * 0.8).toFixed(1)}" fill="url(#l)"/>` +
      `</svg>`,
  )
}

/**
 * Stand-in for a Grad-CAM overlay: warm blobs on a transparent background,
 * so HeatmapViewer can composite it over the source image exactly as it will
 * composite the real `heatmap_url` later.
 */
export function mockHeatmap(seed: number): string {
  const rand = seededRandom(seed + 977)
  const blobs = Array.from({ length: 3 }, (_, i) => ({
    cx: 25 + rand() * 50,
    cy: 25 + rand() * 50,
    r: 28 - i * 7,
    color: ['#dc2626', '#f59e0b', '#fde047'][i],
    opacity: 0.55 - i * 0.12,
  }))

  const gradients = blobs
    .map(
      (b, i) =>
        `<radialGradient id="g${i}"><stop offset="0%" stop-color="${b.color}" stop-opacity="${b.opacity}"/>` +
        `<stop offset="100%" stop-color="${b.color}" stop-opacity="0"/></radialGradient>`,
    )
    .join('')

  const circles = blobs
    .map(
      (b, i) =>
        `<circle cx="${b.cx.toFixed(1)}" cy="${b.cy.toFixed(1)}" r="${b.r}" fill="url(#g${i})"/>`,
    )
    .join('')

  return svgDataUri(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" preserveAspectRatio="none">` +
      `<defs>${gradients}</defs>${circles}</svg>`,
  )
}

const MOCK_GRADES: DysplasiaGrade[] = ['mild', 'moderate', 'severe']

/** Derive a stable grade + cancer label from a filename. */
export function mockInference(filename: string): {
  prediction: PredictionLabel
  dysplasia_grade: DysplasiaGrade
} {
  const rand = seededRandom(hashString(filename))
  const isCancer = rand() > 0.5
  const grade = MOCK_GRADES[Math.floor(rand() * MOCK_GRADES.length)] ?? 'moderate'

  return {
    prediction: isCancer ? 'Cancer' : 'Non-Cancer',
    dysplasia_grade: grade,
  }
}

interface MockRecord extends PredictionOutcome {
  created_at: string
}

function hoursAgo(hours: number): string {
  return new Date(Date.now() - hours * 3600_000).toISOString()
}

const SEED_SPECS: Array<{ hours: number; name: string }> = [
  { hours: 3, name: 'lesion-buccal-01.jpg' },
  { hours: 26, name: 'lesion-tongue-04.png' },
  { hours: 51, name: 'lesion-gingiva-02.jpg' },
  { hours: 74, name: 'lesion-palate-07.jpg' },
  { hours: 120, name: 'lesion-tongue-11.png' },
  { hours: 168, name: 'lesion-lip-03.jpg' },
  { hours: 240, name: 'lesion-floor-05.jpg' },
  { hours: 336, name: 'lesion-buccal-09.png' },
]

function seedRecords(): MockRecord[] {
  return SEED_SPECS.map((spec, index) => {
    const { prediction, dysplasia_grade } = mockInference(spec.name)
    const id = SEED_SPECS.length - index
    return {
      prediction_id: id,
      prediction,
      dysplasia_grade,
      heatmap_url: mockHeatmap(hashString(spec.name)),
      pdf_url: `/reports/${id}.pdf`,
      created_at: hoursAgo(spec.hours),
      filename: spec.name,
      image_url: mockThumbnail(hashString(spec.name)),
      is_pending_inference: false,
    }
  })
}

/**
 * In-memory store, newest first.
 *
 * Lives for the lifetime of the page: uploads made during a session appear in
 * history and are addressable by id, but a hard reload resets to the seed set.
 * Persisting further would be misleading anyway -- the uploaded image is held
 * as an object URL, which cannot survive a reload.
 */
const records: MockRecord[] = seedRecords()

let nextId = records.length + 1

export function allRecords(): MockRecord[] {
  return records
}

export function findRecord(id: number): MockRecord | undefined {
  return records.find((record) => record.prediction_id === id)
}

export function addRecord(file: File, imageUrl: string): MockRecord {
  const { prediction, dysplasia_grade } = mockInference(file.name)
  const id = nextId
  nextId += 1

  const record: MockRecord = {
    prediction_id: id,
    prediction,
    dysplasia_grade,
    heatmap_url: mockHeatmap(hashString(file.name)),
    pdf_url: `/reports/${id}.pdf`,
    created_at: new Date().toISOString(),
    filename: file.name,
    image_url: imageUrl,
    is_pending_inference: false,
  }

  records.unshift(record)
  return record
}

export function toHistoryEntry(record: MockRecord): PredictionHistoryEntry {
  return {
    prediction_id: record.prediction_id,
    prediction: record.prediction as PredictionHistoryEntry['prediction'],
    dysplasia_grade: record.dysplasia_grade,
    created_at: record.created_at,
    image_url: record.image_url,
  }
}
