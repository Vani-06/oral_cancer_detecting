import QRCode from 'qrcode'
import { useEffect, useState } from 'react'

import { disableMfa, enableMfa, myAuditEvents, startMfaSetup } from '@/api/account'
import { ApiError } from '@/api/client'
import type { AuditEvent, MfaSetup } from '@/api/types'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'
import { useAuth } from '@/hooks/useAuth'
import { formatDateTime } from '@/lib/format'

const ACTION_LABELS: Record<string, string> = {
  register: 'Account created',
  login: 'Signed in',
  login_failed: 'Failed sign-in',
  upload: 'Uploaded a photo',
  view: 'Opened an analysis',
  view_photo: 'Viewed a photo',
  view_reference: 'Viewed an opposite-side photo',
  view_heatmap: 'Viewed a heatmap',
  download_report: 'Downloaded a report',
  delete: 'Deleted an analysis',
  feedback: 'Reported a wrong result',
  mfa_enabled: 'Turned on two-factor sign-in',
  mfa_disabled: 'Turned off two-factor sign-in',
  password_reset_requested: 'Asked for a password reset',
  password_reset: 'Changed password by reset link',
}

function describe(action: string): string {
  if (ACTION_LABELS[action]) return ACTION_LABELS[action]
  if (action.startsWith('follow_up_')) return `Follow-up set: ${action.slice(10).replace('_', ' ')}`
  return action.replace(/_/g, ' ')
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.detail : 'Something went wrong. Please try again.'
}

function TwoFactorCard() {
  const { user, updateUser } = useAuth()
  const [setup, setSetup] = useState<MfaSetup | null>(null)
  const [qr, setQr] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!setup) return
    QRCode.toDataURL(setup.otpauth_uri, { margin: 1, width: 192 })
      .then(setQr)
      .catch(() => setQr(null))
  }, [setup])

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (cause) {
      setError(errorText(cause))
    } finally {
      setBusy(false)
    }
  }

  const enabled = Boolean(user?.mfa_enabled)

  return (
    <Card title="Two-factor sign-in">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-slate-600">
          {enabled
            ? 'On. Signing in needs your password and a code from your authenticator app.'
            : 'Off. Turn it on so a stolen password alone cannot open patient records.'}
        </p>

        {!enabled && !setup && (
          <Button
            className="self-start"
            loading={busy}
            onClick={() => run(async () => setSetup(await startMfaSetup()))}
          >
            Set up two-factor sign-in
          </Button>
        )}

        {!enabled && setup && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-slate-700">
              1. Scan this with an authenticator app (Google Authenticator,
              Microsoft Authenticator, 1Password...).
            </p>
            {qr && (
              <img
                src={qr}
                alt="QR code for your authenticator app"
                className="h-48 w-48 self-start rounded border border-slate-200"
              />
            )}
            <p className="text-xs text-slate-500">
              Or enter this key by hand:{' '}
              <code className="rounded bg-slate-100 px-1 py-0.5 font-mono break-all" data-testid="mfa-secret">
                {setup.secret}
              </code>
            </p>
            <p className="text-sm text-slate-700">2. Enter the 6-digit code it shows.</p>
            <Input
              label="Authentication code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
            <Button
              className="self-start"
              loading={busy}
              disabled={code.trim().length < 6}
              onClick={() =>
                run(async () => {
                  updateUser(await enableMfa(code.trim()))
                  setSetup(null)
                  setCode('')
                })
              }
            >
              Turn on
            </Button>
          </div>
        )}

        {enabled && (
          <div className="flex flex-col gap-3">
            <Input
              label="Password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <Input
              label="Authentication code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
            <Button
              variant="secondary"
              className="self-start"
              loading={busy}
              disabled={!password || code.trim().length < 6}
              onClick={() =>
                run(async () => {
                  updateUser(await disableMfa(code.trim(), password))
                  setCode('')
                  setPassword('')
                })
              }
            >
              Turn off
            </Button>
          </div>
        )}

        {error && (
          <p role="alert" className="text-risk-high text-sm">
            {error}
          </p>
        )}
      </div>
    </Card>
  )
}

function AccessLogCard() {
  const [events, setEvents] = useState<AuditEvent[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    myAuditEvents()
      .then(setEvents)
      .catch((cause: unknown) => setError(errorText(cause)))
  }, [])

  return (
    <Card title="Access log">
      <p className="mb-3 text-xs text-slate-500">
        Every sign-in, upload, view, download and deletion on your account (latest 200).
      </p>
      {error ? (
        <p role="alert" className="text-risk-high text-sm">
          {error}
        </p>
      ) : events === null ? (
        <Spinner className="text-brand-600 h-5 w-5" label="Loading access log" />
      ) : events.length === 0 ? (
        <p className="text-sm text-slate-600">No events yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-slate-500">
              <tr>
                <th className="py-1 pr-4 font-medium">When</th>
                <th className="py-1 pr-4 font-medium">What</th>
                <th className="py-1 pr-4 font-medium">Analysis</th>
                <th className="py-1 font-medium">IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {events.map((event, index) => (
                <tr key={`${event.created_at}-${index}`}>
                  <td className="py-1.5 pr-4 whitespace-nowrap text-slate-600">
                    {formatDateTime(event.created_at)}
                  </td>
                  <td className="py-1.5 pr-4 text-slate-800">{describe(event.action)}</td>
                  <td className="py-1.5 pr-4 text-slate-600">
                    {event.prediction_id ? `#${event.prediction_id}` : ''}
                  </td>
                  <td className="py-1.5 font-mono text-xs text-slate-500">{event.ip ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

export function AccountPage() {
  const { user } = useAuth()

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Account</h1>
        <p className="text-sm text-slate-600">
          {user?.full_name} · {user?.email}
        </p>
      </div>
      <TwoFactorCard />
      <AccessLogCard />
    </div>
  )
}
