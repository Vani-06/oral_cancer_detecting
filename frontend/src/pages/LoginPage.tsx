import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { z } from 'zod'

import { ApiError, USE_MOCKS } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useAuth } from '@/hooks/useAuth'

const loginSchema = z.object({
  email: z
    .string()
    .min(1, 'Email is required')
    .refine(
      (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
      'Enter a valid email address',
    ),
  password: z.string().min(1, 'Password is required'),
  mfa_code: z.string().optional(),
})

type LoginValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const { login } = useAuth()
  const [formError, setFormError] = useState<string | null>(null)
  // Shown once the server says this account uses two-factor sign-in.
  const [needsCode, setNeedsCode] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })

  async function onSubmit(values: LoginValues) {
    setFormError(null)
    try {
      // No navigate() here -- PublicOnlyRoute redirects once the user is set,
      // and honours the destination remembered by ProtectedRoute.
      await login({
        email: values.email,
        password: values.password,
        mfa_code: needsCode ? values.mfa_code?.trim() : undefined,
      })
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setNeedsCode(true)
        setFormError(error.detail)
        return
      }
      setFormError(
        error instanceof ApiError
          ? error.detail
          : 'Something went wrong. Please try again.',
      )
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-semibold text-slate-900">OralSentinel</h1>
          <p className="mt-1 text-sm text-slate-600">
            Multimodal oral lesion analysis
          </p>
        </div>

        <form
          onSubmit={handleSubmit(onSubmit)}
          noValidate
          className="bg-surface border-surface-border flex flex-col gap-4 rounded-lg border p-6"
        >
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            placeholder="clinician@example.org"
            error={errors.email?.message}
            {...register('email')}
          />
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            error={errors.password?.message}
            {...register('password')}
          />
          {needsCode && (
            <Input
              label="Authentication code"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="123456"
              hint="The 6-digit code from your authenticator app."
              autoFocus
              {...register('mfa_code')}
            />
          )}

          {formError && (
            <p
              role="alert"
              className="border-risk-high-border bg-risk-high-bg text-risk-high rounded-md border px-3 py-2 text-sm"
            >
              {formError}
            </p>
          )}

          <Button type="submit" loading={isSubmitting} size="lg">
            Sign in
          </Button>

          <Link
            to="/forgot-password"
            className="text-center text-sm text-slate-600 underline"
          >
            Forgot password?
          </Link>

          {USE_MOCKS && (
            <p className="text-center text-xs text-slate-500">
              Mock mode: any email and password will sign you in.
            </p>
          )}
        </form>

        <p className="mt-4 text-center text-sm text-slate-600">
          No account?{' '}
          <Link to="/register" className="text-brand-700 font-medium underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
  )
}
