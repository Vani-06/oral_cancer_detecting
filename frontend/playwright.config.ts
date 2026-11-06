/**
 * End-to-end test: the real React app against the real FastAPI backend and
 * the real models, in the system Chrome. Both servers are started on spare
 * ports with a throwaway SQLite database and upload folder, so the dev
 * database is untouched.
 *
 *   npm run test:e2e
 *
 * Needs backend/.venv and the model files in ml/artifacts (see README).
 */

import { defineConfig } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const ROOT = resolve(import.meta.dirname, '..')
const ARTIFACTS = join(ROOT, 'ml', 'artifacts')
const WORK = mkdtempSync(join(tmpdir(), 'oralsentinel-e2e-'))
const PYTHON =
  process.platform === 'win32'
    ? join(ROOT, 'backend', '.venv', 'Scripts', 'python.exe')
    : join(ROOT, 'backend', '.venv', 'bin', 'python')

const API_PORT = 8011
const WEB_PORT = 5181

export default defineConfig({
  testDir: './e2e',
  timeout: 180_000,
  expect: { timeout: 30_000 },
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    channel: process.env.PW_CHANNEL ?? 'chrome',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `"${PYTHON}" -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: join(ROOT, 'backend'),
      url: `http://localhost:${API_PORT}/config/public`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: {
        ENVIRONMENT: 'development',
        DATABASE_URL: `sqlite:///${join(WORK, 'e2e.db').replace(/\\/g, '/')}`,
        AUTO_CREATE_TABLES: 'true',
        UPLOAD_DIR: join(WORK, 'uploads'),
        REPORT_DIR: join(WORK, 'reports'),
        CORS_ORIGINS: `http://localhost:${WEB_PORT}`,
        REGISTRATION_MODE: 'open',
        MODEL_PATH: join(ARTIFACTS, 'resnet50_oral_cancer_v7.pt'),
        GRADING_MODEL_PATH: join(ARTIFACTS, 'resnet50_dysplasia_grade_v2.pt'),
        // The fixture photo is synthetic (no patient data), so the
        // oral-photo check would rightly refuse it; it is tested in the backend suite.
        GATE_MODEL_PATH: '',
      },
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      timeout: 60_000,
      reuseExistingServer: false,
      env: { VITE_API_BASE_URL: `http://localhost:${API_PORT}`, VITE_USE_MOCKS: 'false' },
    },
  ],
})
