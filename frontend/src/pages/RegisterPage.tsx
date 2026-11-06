import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { z } from 'zod'

import { publicConfig } from '@/api/account'
import { ApiError } from '@/api/client'
import type { PublicConfig } from '@/api/types'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useAuth } from '@/hooks/useAuth'

const registerSchema = z.object({
  full_name: z.string().min(2, 'Enter your full name'),
  email: z
    .string()
    .min(1, 'Email is required')
    .refine(
      (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
      'Enter a valid email address',
    ),
  password: z.string().min(8, 'Use at least 8 characters'),
  confirms_professional_use: z.literal(true, {
    error: 'Please confirm to create an account',
  }),
  invite_code: z.string().optional(),
})

type RegisterValues = z.infer<typeof registerSchema>

export function RegisterPage() {
  const { register: createAccount } = useAuth()
  const [formError, setFormError] = useState<string | null>(null)
  const [config, setConfig] = useState<PublicConfig | null>(null)

  // How sign-up is restricted on this server (open, invite code, or domain).
  useEffect(() => {
    publicConfig().then(setConfig).catch(() => setConfig(null))
  }, [])
  const inviteOnly = config?.registration_mode === 'invite'

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) })

  async function onSubmit(values: RegisterValues) {
    setFormError(null)
    try {
      // PublicOnlyRoute performs the redirect once the user is set.
      await createAccount({
        ...values,
        invite_code: inviteOnly ? values.invite_code?.trim() : undefined,
      })
    } catch (error) {
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
          <h1 className="text-2xl font-semibold text-slate-900">
            Create account
          </h1>
        </div>

        <form
          onSubmit={handleSubmit(onSubmit)}
          noValidate
          className="bg-surface border-surface-border flex flex-col gap-4 rounded-lg border p-6"
        >
          <Input
            label="Full name"
            autoComplete="name"
            error={errors.full_name?.message}
            {...register('full_name')}
          />
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            {...register('email')}
          />
          {inviteOnly && (
            <Input
              label="Invitation code"
              autoComplete="off"
              hint="Sign-up on this server is by invitation. Ask the administrator for a code."
              {...register('invite_code')}
            />
          )}
          {config?.registration_mode === 'domain' && (
            <p className="text-xs text-slate-500">
              Sign-up is limited to approved institutional email addresses.
            </p>
          )}
          <Input
            label="Password"
            type="password"
            autoComplete="new-password"
            hint="At least 8 characters."
            error={errors.password?.message}
            {...register('password')}
          />

          <label className="flex items-start gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4"
              {...register('confirms_professional_use')}
            />
            <span>
              I am a health professional and have the patient's consent to
              upload their photos. I understand OralSentinel is a research
              prototype and not a diagnosis.
            </span>
          </label>
          {errors.confirms_professional_use && (
            <p className="text-risk-high text-sm">
              {errors.confirms_professional_use.message}
            </p>
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
            Create account
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-slate-600">
          Already registered?{' '}
          <Link to="/login" className="text-brand-700 font-medium underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
