/**
 * The whole clinician journey through the real app, backend and models:
 * sign up, analyse a photo (consent required), record follow-up, report a
 * wrong result, turn on two-factor sign-in, sign back in with a code, check
 * the access log, and delete the analysis.
 */

import { expect, test, type Page } from '@playwright/test'
import { createHmac } from 'node:crypto'
import { join } from 'node:path'

const PHOTO = join(import.meta.dirname, 'fixtures', 'synthetic-lesion.jpg')

/** Set E2E_SCREENSHOTS=<folder> to save full-page screenshots of each screen. */
async function snap(page: Page, name: string) {
  const dir = process.env.E2E_SCREENSHOTS
  if (dir) await page.screenshot({ path: join(dir, `${name}.png`), fullPage: true })
}

/** RFC 6238 code for a base32 secret, as an authenticator app would show. */
function totp(secret: string, now = Date.now()): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const char of secret.replace(/=+$/, '').toUpperCase()) {
    bits += alphabet.indexOf(char).toString(2).padStart(5, '0')
  }
  const key = Buffer.from(bits.match(/.{8}/g)!.map((byte) => parseInt(byte, 2)))
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(Math.floor(now / 1000 / 30)))
  const hmac = createHmac('sha1', key).update(counter).digest()
  const offset = hmac[hmac.length - 1] & 0xf
  const value = (hmac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000
  return value.toString().padStart(6, '0')
}

async function answer(page: Page, question: string, choice: 'Yes' | 'No') {
  await page.getByRole('group', { name: question }).getByText(choice, { exact: true }).click()
}

test('clinician workflow end to end', async ({ page }) => {
  const email = `e2e-${Date.now()}@clinic.test`
  const password = 'e2e-password-123'

  // Sign up.
  await page.goto('/register')
  await page.getByLabel('Full name').fill('Dr E2E Test')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()

  // New analysis: photo and patient details.
  await page.getByRole('link', { name: 'New Analysis' }).first().click()
  await page.locator('input[type="file"]').first().setInputFiles(PHOTO)
  await page.getByLabel('Age').fill('52')
  await page.getByLabel('Sex').selectOption('male')
  await answer(page, 'Tobacco use', 'No')
  await answer(page, 'Betel quid / areca nut / pan', 'No')
  await answer(page, 'Alcohol use', 'No')
  await page.getByLabel('Site', { exact: true }).selectOption('buccal_mucosa')
  await answer(page, 'Pain', 'No')
  await answer(page, 'Bleeding', 'No')
  await answer(page, 'History of prior oral lesions', 'No')

  // Consent is required before anything is uploaded.
  await page.getByRole('button', { name: 'Run analysis' }).click()
  await expect(page.getByText('Confirm that the patient has consented')).toBeVisible()
  await page.getByLabel(/patient has consented/).check()
  await page.getByRole('button', { name: 'Run analysis' }).click()

  await expect(page.getByRole('heading', { name: 'Analysis result' })).toBeVisible({ timeout: 150_000 })
  const resultUrl = page.url()
  await expect(page.getByText('Analysis version:')).toBeVisible()
  await expect(page.getByText(/Patient consent confirmed/)).toBeVisible()

  // Follow-up and wrong-result report.
  await page.getByLabel('Note (optional)').fill('Reviewed in clinic, benign appearance')
  await page.getByRole('button', { name: 'Closed' }).click()
  await expect(page.getByTestId('follow-up-status')).toHaveText('Closed')
  await page.getByLabel('What was wrong').selectOption('grade_wrong')
  await page.getByRole('button', { name: 'Send report' }).click()
  await expect(page.getByText('Thank you, the report was saved.')).toBeVisible()
  await snap(page, '1-result')

  // Two-factor sign-in.
  await page.getByRole('link', { name: 'Account' }).first().click()
  await page.getByRole('button', { name: 'Set up two-factor sign-in' }).click()
  await expect(page.getByAltText('QR code for your authenticator app')).toBeVisible()
  await snap(page, '2-mfa-setup')
  const secret = (await page.getByTestId('mfa-secret').textContent())!.trim()
  await page.getByLabel('Authentication code').fill(totp(secret))
  await page.getByRole('button', { name: 'Turn on' }).click()
  await expect(page.getByText(/^On\. Signing in needs/)).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Uploaded a photo' })).toBeVisible()

  // Sign out and back in: the password alone is no longer enough.
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toContainText('6-digit code')
  await snap(page, '3-sign-in-code')
  await page.getByLabel('Authentication code').fill(totp(secret))
  await page.getByRole('button', { name: 'Sign in' }).click()
  // Signed in again, back on the page where the user signed out.
  await expect(page.getByRole('heading', { name: 'Account', level: 1 })).toBeVisible()

  // Delete the analysis; it is gone afterwards.
  await page.goto(resultUrl)
  await page.getByRole('button', { name: 'Delete analysis' }).click()
  await page.getByRole('button', { name: 'Yes, delete permanently' }).click()
  await expect(page).toHaveURL(/\/history$/)
  await page.goto(resultUrl)
  await expect(page.getByRole('heading', { name: 'Prediction unavailable' })).toBeVisible()
})
