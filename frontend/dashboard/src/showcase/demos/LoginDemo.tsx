import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { LoginForm, BackButton, type LoginValues } from '@/components/shared'
import { useAuth } from '@/context/AuthContext'
import { BASE } from '../base'
import { makeFakeJwt } from '../_kit/fakeJwt'

const LoginDemo = () => {
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async ({ username, password }: LoginValues) => {
    await new Promise((r) => setTimeout(r, 800)) // pretend network
    if (password !== 'demo') throw new Error('wrong password')
    login(makeFakeJwt({ sub: '1', name: username, role: 'admin' }))
    toast.success(`Logged in as ${username}`)
    navigate(`${BASE}/auth`)
  }

  return (
    <>
      <LoginForm
        brand={<h1 className="text-3xl font-black">Showcase</h1>}
        description="Any username, password “demo”. Anything else shows the error state."
        onSubmit={handleSubmit}
      />
      <div className="fixed top-4 left-4">
        <BackButton to={`${BASE}/components#login-form`} label="Back to docs" />
      </div>
    </>
  )
}

export default LoginDemo
