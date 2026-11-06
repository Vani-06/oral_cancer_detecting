import { createContext } from 'react'

import type { LoginRequest, RegisterRequest, User } from '@/api/types'

export interface AuthContextValue {
  user: User | null
  /** True while the stored token is being exchanged for a user on first load. */
  initialising: boolean
  login: (credentials: LoginRequest) => Promise<void>
  register: (payload: RegisterRequest) => Promise<void>
  logout: () => void
  /** Replace the signed-in user, e.g. after two-factor sign-in is turned on. */
  updateUser: (user: User) => void
}

/**
 * Kept in its own module, separate from the provider component, so the file
 * exporting the provider exports components only -- react-refresh cannot do a
 * fast refresh of a module that mixes components with other exports.
 */
export const AuthContext = createContext<AuthContextValue | null>(null)
