import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { TOKEN_KEY, UNAUTHORIZED_EVENT } from '@/utils/api/client'
import { decodeJwt, getJwtRoles, isJwtExpired } from '@/utils/jwt'
import { AuthContext, type AuthContextValue } from './AuthContext'

function readStoredToken(): string | null {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token && isJwtExpired(token)) {
    localStorage.removeItem(TOKEN_KEY)
    return null
  }
  return token
}

const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [token, setToken] = useState(readStoredToken)

  const login = useCallback((newToken: string) => {
    localStorage.setItem(TOKEN_KEY, newToken)
    setToken(newToken)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
  }, [])

  // The axios interceptor fires this on a 401 for an authenticated request
  useEffect(() => {
    window.addEventListener(UNAUTHORIZED_EVENT, logout)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, logout)
  }, [logout])

  const value = useMemo<AuthContextValue>(() => {
    const claims = token ? decodeJwt(token) : {}
    return { token, claims, roles: getJwtRoles(claims), isAuthenticated: token !== null, login, logout }
  }, [token, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export default AuthProvider
