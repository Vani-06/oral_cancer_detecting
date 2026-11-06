import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { confirmPasswordReset, requestPasswordReset } from '@/api/account'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

function Shell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-6 text-center text-2xl font-semibold text-slate-900">{title}</h1>
        <div className="bg-surface border-surface-border flex flex-col gap-4 rounded-lg border p-6">
          {children}
        </div>
        <p className="mt-4 text-center text-sm text-slate-600">
          <Link to="/login" className="text-brand-700 font-medium underline">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  )
}

function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="border-risk-high-border bg-risk-high-bg text-risk-high rounded-md border px-3 py-2 text-sm"
    >
      {children}
    </p>
  )
}

function message(error: unknown): string {
  return error instanceof ApiError ? error.detail : 'Something went wrong. Please try again.'
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const response = await requestPasswordReset(email.trim())
      setSent(response.detail)
    } catch (cause) {
      setError(message(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell title="Reset password">
      {sent ? (
        <p role="status" className="text-sm text-slate-700">
          {sent}
        </p>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          <p className="text-sm text-slate-600">
            Enter your account email. If it is registered, a one-time link to
            set a new password will be sent to it.
          </p>
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          {error && <ErrorText>{error}</ErrorText>}
          <Button type="submit" loading={busy} disabled={!email.includes('@')}>
            Send reset link
          </Button>
        </form>
      )}
    </Shell>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (password.length < 8) return setError('Use at least 8 characters.')
    if (password !== confirm) return setError('The two passwords do not match.')
    setError(null)
    setBusy(true)
    try {
      await confirmPasswordReset(token, password)
      setDone(true)
    } catch (cause) {
      setError(message(cause))
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return (
      <Shell title="Reset password">
        <ErrorText>This link is incomplete. Open the link from the email again.</ErrorText>
      </Shell>
    )
  }

  return (
    <Shell title="Choose a new password">
      {done ? (
        <p role="status" className="text-sm text-slate-700">
          Your password was changed. You can now sign in with it.
        </p>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          <Input
            label="New password"
            type="password"
            autoComplete="new-password"
            hint="At least 8 characters."
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Input
            label="Repeat new password"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
          {error && <ErrorText>{error}</ErrorText>}
          <Button type="submit" loading={busy}>
            Set new password
          </Button>
        </form>
      )}
    </Shell>
  )
}
