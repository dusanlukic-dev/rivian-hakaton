import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '@/context/AuthContext'
import { API_BASE_URL, TOKEN_KEY, UNAUTHORIZED_EVENT } from '@/utils/api/client'
import { decodeJwt, getJwtRoles, isJwtExpired } from '@/utils/jwt'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { BASE } from '../base'
import { makeFakeJwt } from '../_kit/fakeJwt'
import { Code, Demo, DocPage, DocSection, P, Props, Readout } from '../_kit/Doc'

const AuthApiPage = () => {
  const { isAuthenticated, roles, claims, login, logout } = useAuth()
  const [jwtInput, setJwtInput] = useState(() =>
    makeFakeJwt({ sub: '42', name: 'Đorđe Šaljić', 'http://schemas.microsoft.com/ws/2008/06/identity/claims/role': 'tenant_admin', tenantId: 3 })
  )
  const decoded = decodeJwt(jwtInput.trim())

  const fakeLogin = (role: string) => {
    login(makeFakeJwt({ sub: '1', name: `Demo ${role}`, role }))
    toast.success(`Logged in as ${role} (fake token)`)
  }

  const simulate401 = () => {
    // Exactly what the axios interceptor does on a 401
    localStorage.removeItem(TOKEN_KEY)
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    toast('401 → logged out')
  }

  return (
    <DocPage
      title="Auth & API"
      intro="JWT auth from end to end: axios attaches the token, a 401 logs you out, AuthContext exposes the decoded claims, and RequireAuth guards routes."
      toc={[['auth-context', 'AuthProvider / useAuth'], ['api-client', 'axios client'], ['jwt', 'JWT helpers']]}
    >
      <DocSection id="auth-context" title="AuthProvider / useAuth" importLine="import { AuthProvider, useAuth } from '@/context/AuthContext'">
        <P>
          <code>AuthProvider</code> wraps the router in <code>App.tsx</code>. The token lives in React state and in localStorage under <code>{TOKEN_KEY}</code>.
          An expired token is discarded when the app loads. During a session, expiry is enforced by the backend's 401, which the axios interceptor turns into a logout.
          The login buttons below use unsigned fake tokens. That's enough for the frontend, since it never verifies signatures.
        </P>
        <Demo className="flex-col items-stretch">
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={() => fakeLogin('admin')}>Fake login: admin</Button>
            <Button size="sm" variant="outline" onClick={() => fakeLogin('user')}>Fake login: user</Button>
            <Button size="sm" variant="outline" onClick={simulate401} disabled={!isAuthenticated}>Simulate 401</Button>
            <Button size="sm" variant="ghost" onClick={logout} disabled={!isAuthenticated}>logout()</Button>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Readout label="isAuthenticated:">{String(isAuthenticated)}</Readout>
            <Readout label="roles:">{roles.length ? roles.join(', ') : '[]'}</Readout>
          </div>
          <pre className="no-scrollbar overflow-x-auto rounded-md bg-muted/40 p-3 font-mono text-[11px]">{JSON.stringify(claims, null, 2)}</pre>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" asChild><Link to="/admin">Open /admin (RequireAuth) →</Link></Button>
            <Button size="sm" variant="outline" asChild><Link to={`${BASE}/demo/login`}>Open login demo →</Link></Button>
          </div>
          <p className="text-[11px] text-muted-foreground">Logged out, <code>/admin</code> redirects to <code>/login</code>. That's the real LoginPage, which posts to your backend.</p>
        </Demo>
        <Code>{`
          const { isAuthenticated, roles, claims, token, login, logout } = useAuth()

          // after your login request:
          login(data.token)

          // role checks in UI (route-level → <RequireAuth roles={[…]} />)
          {roles.includes('admin') && <Button>Delete</Button>}
          const tenantId = Number(claims.tenantId)
        `}</Code>
        <Props rows={[
          ['token', 'string | null', '', 'Raw JWT'],
          ['claims', 'Record<string, unknown>', '{}', 'Decoded payload'],
          ['roles', 'string[]', '[]', "From 'role' or the ASP.NET role claim URI. A single value or an array"],
          ['isAuthenticated', 'boolean', '', 'token !== null'],
          ['login(token)', '(token: string) => void', '', 'Store + set state. RequireAuth/LoginPage react to it'],
          ['logout()', '() => void', '', 'Clear token. Guards redirect'],
        ]} />
      </DocSection>

      <DocSection id="api-client" title="axios client" importLine="import api, { API_BASE_URL, TOKEN_KEY, UNAUTHORIZED_EVENT } from '@/utils/api/client'">
        <P>
          A preconfigured axios instance. It adds <code>Authorization: Bearer &lt;token&gt;</code> when a token exists, and sends <code>ngrok-skip-browser-warning</code>.
          On a 401 for an authenticated request it clears the token and fires <code>{UNAUTHORIZED_EVENT}</code>, which makes AuthProvider log out.
          The base URL is empty in dev, where Vite proxies <code>/api</code> and <code>/hubs</code> to <code>VITE_API_URL</code>, and <code>VITE_API_URL</code> itself in production.
        </P>
        <Demo>
          <Readout label="API_BASE_URL:">{API_BASE_URL === '' ? "'' (dev → Vite proxy)" : API_BASE_URL}</Readout>
          <Readout label="mode:">{import.meta.env.MODE}</Readout>
          <Badge variant="outline">{isAuthenticated ? 'requests carry a Bearer token' : 'no token → no Authorization header'}</Badge>
        </Demo>
        <Code title="Pattern: one file per resource in src/utils/api/">{`
          // src/utils/api/teams.ts
          import api from './client'

          export type Team = { id: number; name: string }

          export const getTeams = () => api.get<Team[]>('/api/teams')
          export const getTeam = (id: number) => api.get<Team>(\`/api/teams/\${id}\`)
          export const createTeam = (payload: Omit<Team, 'id'>) => api.post<Team>('/api/teams', payload)

          // in a component
          const { data } = await getTeams()
        `}</Code>
        <Code title="Error handling">{`
          import axios from 'axios'

          try {
            await createTeam(values)
          } catch (err) {
            const msg = axios.isAxiosError(err) ? err.response?.data?.message ?? err.message : 'Unknown error'
            toast.error(msg)
          }
        `}</Code>
      </DocSection>

      <DocSection id="jwt" title="JWT helpers" importLine="import { decodeJwt, isJwtExpired, getJwtRoles } from '@/utils/jwt'">
        <P>
          Client-side decoding only, with <strong>no signature verification</strong>. It's for reading claims in the UI and never for security.
          It handles UTF-8 (š, đ, č…) and ASP.NET's long role claim URI. Paste any token:
        </P>
        <Demo className="flex-col items-stretch">
          <Textarea className="font-mono text-[11px]" rows={3} value={jwtInput} onChange={(e) => setJwtInput(e.target.value)} />
          <div className="flex flex-wrap gap-4">
            <Readout label="getJwtRoles:">{JSON.stringify(getJwtRoles(decoded))}</Readout>
            <Readout label="isJwtExpired:">{String(isJwtExpired(jwtInput.trim()))}</Readout>
          </div>
          <pre className="no-scrollbar overflow-x-auto rounded-md bg-muted/40 p-3 font-mono text-[11px]">{JSON.stringify(decoded, null, 2)}</pre>
        </Demo>
        <Code>{`
          decodeJwt(token)        // → claims object, or {} if malformed
          isJwtExpired(token)     // → true if exp is in the past (false when there's no exp)
          getJwtRoles(claims)     // → string[]
        `}</Code>
      </DocSection>
    </DocPage>
  )
}

export default AuthApiPage
