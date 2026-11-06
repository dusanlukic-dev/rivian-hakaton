import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

type RequireAuthProps = {
  /** If set, the user needs at least one of these roles */
  roles?: string[]
  redirectTo?: string
  /** Where users without the right role go */
  forbiddenTo?: string
}

/**
 * Layout route guard. Unauthenticated users go to `redirectTo` with `state.from` set,
 * so the login page can send them back afterwards.
 */
const RequireAuth = ({ roles, redirectTo = '/login', forbiddenTo = '/' }: RequireAuthProps) => {
  const { isAuthenticated, roles: userRoles } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) return <Navigate to={redirectTo} replace state={{ from: location }} />
  if (roles && !roles.some((role) => userRoles.includes(role))) return <Navigate to={forbiddenTo} replace />
  return <Outlet />
}

export default RequireAuth
