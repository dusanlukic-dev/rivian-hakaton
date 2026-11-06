import { Navigate, useLocation, type Location } from 'react-router-dom'
import { LoginForm, type LoginValues } from '@/components/shared'
import { useAuth } from '@/context/AuthContext'
import api from '@/utils/api/client'

/** Example wiring of LoginForm + AuthProvider — change the endpoint/response shape to match your backend. */
const LoginPage = () => {
  const { isAuthenticated, login } = useAuth()
  const location = useLocation()
  // Set by RequireAuth when it bounced the user here
  const from = (location.state as { from?: Location } | null)?.from?.pathname ?? '/admin'

  if (isAuthenticated) return <Navigate to={from} replace />

  const handleSubmit = async (values: LoginValues) => {
    const { data } = await api.post<{ token: string }>('/api/auth/login', values)
    login(data.token) // re-renders into the <Navigate> above
  }

  return <LoginForm brand={<h1 className="text-3xl font-black">App</h1>} onSubmit={handleSubmit} />
}

export default LoginPage
