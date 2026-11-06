import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { mockFetch, route } from '@/test/fetchMock'
import { renderAt } from '@/test/render'
import { LoginPage } from './LoginPage'
import { ForgotPasswordPage, ResetPasswordPage } from './PasswordResetPages'
import { RegisterPage } from './RegisterPage'

const USER = { id: 1, email: 'dr@clinic.org', full_name: 'Dr Test', mfa_enabled: true }

describe('sign in', () => {
  it('asks for the authenticator code when the account uses two-factor sign-in', async () => {
    const user = userEvent.setup()
    const calls = mockFetch((call) => {
      if (call.method !== 'POST' || !call.url.endsWith('/login')) return undefined
      const body = call.body as { mfa_code?: string }
      return body.mfa_code
        ? { status: 200, body: { access_token: 't', token_type: 'bearer', user: USER } }
        : { status: 403, body: { detail: 'Enter the 6-digit code from your authenticator app.' } }
    })
    renderAt('/login', <LoginPage />)

    expect(screen.queryByLabelText('Authentication code')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Email'), 'dr@clinic.org')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('6-digit code')
    await user.type(screen.getByLabelText('Authentication code'), '123456')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(calls).toHaveLength(2))
    expect(calls[1].body).toMatchObject({ email: 'dr@clinic.org', mfa_code: '123456' })
  })

  it('shows the server message for a wrong password', async () => {
    const user = userEvent.setup()
    mockFetch(route('POST', '/login', 401, { detail: 'Invalid email or password' }))
    renderAt('/login', <LoginPage />)
    await user.type(screen.getByLabelText('Email'), 'dr@clinic.org')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
  })
})

describe('sign up', () => {
  it('asks for an invitation code when sign-up is invite-only, and sends it', async () => {
    const user = userEvent.setup()
    const calls = mockFetch(
      route('GET', '/config/public', 200, {
        allow_registration: true,
        registration_mode: 'invite',
        password_reset_by_email: true,
      }),
      route('POST', '/register', 400, { detail: 'This invitation code is invalid, used or expired.' }),
    )
    renderAt('/register', <RegisterPage />)

    const code = await screen.findByLabelText('Invitation code')
    await user.type(screen.getByLabelText('Full name'), 'Dr Test')
    await user.type(screen.getByLabelText('Email'), 'dr@clinic.org')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.type(code, ' ABC123 ')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('invitation code is invalid')
    const register = calls.find((call) => call.url.endsWith('/register'))
    expect(register?.body).toMatchObject({ invite_code: 'ABC123', confirms_professional_use: true })
  })

  it('has no invitation field when sign-up is open', async () => {
    mockFetch(
      route('GET', '/config/public', 200, {
        allow_registration: true,
        registration_mode: 'open',
        password_reset_by_email: false,
      }),
    )
    renderAt('/register', <RegisterPage />)
    await screen.findByLabelText('Full name')
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(screen.queryByLabelText('Invitation code')).not.toBeInTheDocument()
  })
})

describe('password reset', () => {
  it('shows the same neutral message after a reset request', async () => {
    const user = userEvent.setup()
    mockFetch(
      route('POST', '/password-reset/request', 202, {
        detail: 'If that email has an account, a reset link has been sent.',
      }),
    )
    renderAt('/forgot-password', <ForgotPasswordPage />)
    await user.type(screen.getByLabelText('Email'), 'dr@clinic.org')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByRole('status')).toHaveTextContent('If that email has an account')
  })

  it('sets a new password with the token from the link', async () => {
    const user = userEvent.setup()
    const calls = mockFetch(route('POST', '/password-reset/confirm', 200, { detail: 'ok' }))
    renderAt('/reset-password?token=tok123', <ResetPasswordPage />)
    await user.type(screen.getByLabelText('New password'), 'newpassword1')
    await user.type(screen.getByLabelText('Repeat new password'), 'newpassword2')
    await user.click(screen.getByRole('button', { name: 'Set new password' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('do not match')
    expect(calls).toHaveLength(0)

    await user.clear(screen.getByLabelText('Repeat new password'))
    await user.type(screen.getByLabelText('Repeat new password'), 'newpassword1')
    await user.click(screen.getByRole('button', { name: 'Set new password' }))
    expect(await screen.findByRole('status')).toHaveTextContent('password was changed')
    expect(calls[0].body).toEqual({ token: 'tok123', new_password: 'newpassword1' })
  })
})
