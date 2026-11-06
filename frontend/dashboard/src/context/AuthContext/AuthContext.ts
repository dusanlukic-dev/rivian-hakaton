import { createContext } from 'react'
import type { JwtClaims } from '@/utils/jwt'

export type AuthContextValue = {
  token: string | null
  claims: JwtClaims
  roles: string[]
  isAuthenticated: boolean
  /** Store the token returned by your login endpoint */
  login: (token: string) => void
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
