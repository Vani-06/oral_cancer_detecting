/**
 * Account security: sign-up settings, two-factor sign-in, password reset and
 * the user's own access log.
 */

import { getJson, postJson, USE_MOCKS } from './client'
import type { AuditEvent, MfaSetup, PublicConfig, User } from './types'

const MOCK_CONFIG: PublicConfig = {
  allow_registration: true,
  registration_mode: 'open',
  password_reset_by_email: false,
}

export function publicConfig(): Promise<PublicConfig> {
  if (USE_MOCKS) return Promise.resolve(MOCK_CONFIG)
  return getJson<PublicConfig>('/config/public')
}

export function startMfaSetup(): Promise<MfaSetup> {
  return postJson<MfaSetup>('/mfa/setup', {})
}

export function enableMfa(code: string): Promise<User> {
  return postJson<User>('/mfa/enable', { code })
}

export function disableMfa(code: string, password: string): Promise<User> {
  return postJson<User>('/mfa/disable', { code, password })
}

export function requestPasswordReset(email: string): Promise<{ detail: string }> {
  return postJson<{ detail: string }>('/password-reset/request', { email })
}

export function confirmPasswordReset(token: string, newPassword: string): Promise<unknown> {
  return postJson('/password-reset/confirm', { token, new_password: newPassword })
}

export function myAuditEvents(): Promise<AuditEvent[]> {
  if (USE_MOCKS) return Promise.resolve([])
  return getJson<AuditEvent[]>('/me/audit')
}
