import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import * as authApi from '@/api/auth'
import { clearToken, getToken } from '@/api/client'
import type { LoginRequest, RegisterRequest, User } from '@/api/types'
import { AuthContext, type AuthContextValue } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  // With no stored token there is nothing to wait for, so start settled rather
  // than rendering a spinner for one frame and clearing it from an effect.
  const [initialising, setInitialising] = useState(() => getToken() !== null)

  // On first load, exchange any stored token for the current user. A token that
  // the server no longer accepts is discarded rather than left to fail later.
  useEffect(() => {
    if (!getToken()) return

    let cancelled = false

    authApi
      .me()
      .then((currentUser) => {
        if (!cancelled) setUser(currentUser)
      })
      .catch(() => {
        clearToken()
      })
      .finally(() => {
        if (!cancelled) setInitialising(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (credentials: LoginRequest) => {
    const response = await authApi.login(credentials)
    setUser(response.user)
  }, [])

  const register = useCallback(async (payload: RegisterRequest) => {
    const response = await authApi.register(payload)
    setUser(response.user)
  }, [])

  const logout = useCallback(() => {
    authApi.logout()
    setUser(null)
  }, [])

  const updateUser = useCallback((next: User) => setUser(next), [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, initialising, login, register, logout, updateUser }),
    [user, initialising, login, register, logout, updateUser],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}
