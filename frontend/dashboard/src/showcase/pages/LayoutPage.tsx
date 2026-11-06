import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Home01Icon, Search01Icon, Ticket01Icon, UserIcon } from '@hugeicons/core-free-icons'
import { MobileNav } from '@/components/layout'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { BASE } from '../base'
import { Code, Demo, DocPage, DocSection, P, Props } from '../_kit/Doc'

type Tab = 'home' | 'search' | 'tickets' | 'profile'

const LayoutPage = () => {
  const [tab, setTab] = useState<Tab>('home')
  const [hasTicket, setHasTicket] = useState(true)

  return (
    <DocPage
      title="Layout"
      intro={<>Page shells from <code>@/components/layout</code>. They're re-exported from one barrel (and again from <code>@/components</code>), so you can import everything in a single line.</>}
      toc={[['phone-frame', 'PhoneFrame'], ['mobile-nav', 'MobileNav'], ['sidebar-layout', 'SidebarLayout'], ['require-auth', 'RequireAuth']]}
    >
      <DocSection id="phone-frame" title="PhoneFrame" importLine="import { PhoneFrame } from '@/components/layout'">
        <P>
          Wraps the app in an iPhone frame (Dynamic Island and home indicator) for demoing a mobile app on a laptop or projector.
          Below the <code>sm</code> breakpoint the frame disappears and the app goes full-screen, so the same build works on real phones.
          It's <code>position: fixed</code> over the whole viewport, which is why the demo opens on its own page.
        </P>
        <Demo>
          <Button asChild><Link to={`${BASE}/demo/phone`}>Open full-screen demo →</Link></Button>
          <span className="text-xs text-muted-foreground">SplashScreen → Onboarding → app with MobileNav, all inside a PhoneFrame</span>
        </Demo>
        <Code title="The classic hackathon mobile-app flow (what the demo does)">{`
          const [stage, setStage] = useState<'splash' | 'onboarding' | 'app'>('splash')
          useEffect(() => {
            const t = setTimeout(() => setStage('onboarding'), 2500)
            return () => clearTimeout(t)
          }, [])

          <PhoneFrame>
            <AnimatePresence mode="wait">
              {stage === 'splash' && (
                <motion.div key="splash" className="size-full" exit={{ opacity: 0, scale: 0.95 }}>
                  <SplashScreen><h1 className="text-4xl font-black">App</h1></SplashScreen>
                </motion.div>
              )}
              {stage === 'onboarding' && (
                <motion.div key="onb" className="size-full" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                  <Onboarding steps={steps} onFinish={() => setStage('app')} />
                </motion.div>
              )}
              {stage === 'app' && (
                <motion.div key="app" className="flex h-full flex-col" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <div className="no-scrollbar flex-1 overflow-y-auto">{/* page */}</div>
                  <MobileNav items={tabs} active={tab} onChange={setTab} />
                </motion.div>
              )}
            </AnimatePresence>
          </PhoneFrame>
        `}</Code>
        <P>The scroll container inside the frame has <code>id="phone-container"</code>, in case you need to scroll it programmatically.</P>
      </DocSection>

      <DocSection id="mobile-nav" title="MobileNav" importLine="import { MobileNav, type MobileNavItem } from '@/components/layout'">
        <P>
          Bottom tab bar. It's controlled: you own the active tab. It sticks to the bottom of its scroll container (<code>sticky bottom-0 mt-auto</code>),
          so put it last in a <code>flex flex-col</code> parent. The active tab gets a heavier stroke and bold label, and <code>badge</code> adds a dot.
        </P>
        <Demo className="flex-col items-start">
          <div className="flex h-72 w-80 flex-col overflow-hidden rounded-xl border">
            <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
              Current tab: <span className="ml-1 font-mono font-semibold text-foreground">{tab}</span>
            </div>
            <MobileNav<Tab>
              active={tab}
              onChange={setTab}
              className="pb-4"
              items={[
                { key: 'home', label: 'Početna', icon: Home01Icon },
                { key: 'search', label: 'Pretraga', icon: Search01Icon },
                { key: 'tickets', label: 'Tiketi', icon: Ticket01Icon, badge: hasTicket },
                { key: 'profile', label: 'Profil', icon: UserIcon },
              ]}
            />
          </div>
          <Label className="gap-2"><Switch checked={hasTicket} onCheckedChange={setHasTicket} />badge on "Tiketi"</Label>
        </Demo>
        <Code>{`
          type Tab = 'home' | 'search' | 'tickets'
          const [tab, setTab] = useState<Tab>('home')

          <MobileNav<Tab> active={tab} onChange={setTab} items={[
            { key: 'home', label: 'Home', icon: Home01Icon },
            { key: 'search', label: 'Search', icon: Search01Icon },
            { key: 'tickets', label: 'Tickets', icon: Ticket01Icon, badge: hasActiveTicket },
          ]} />

          // To drive it from the URL instead:  active={pathname}  onChange={navigate}
        `}</Code>
        <Props rows={[
          ['items', 'MobileNavItem<K>[]', '', '{ key, label, icon (Hugeicon), badge? }'],
          ['active', 'K', '', 'Key of the selected tab'],
          ['onChange', '(key: K) => void', '', 'Called with the clicked key'],
          ['className', 'string', '', 'Merged via cn(). Default bottom padding is pb-8 to clear the iOS home indicator'],
        ]} />
      </DocSection>

      <DocSection id="sidebar-layout" title="SidebarLayout + SidebarButton" importLine="import { SidebarLayout, SidebarButton, type SidebarNavItem } from '@/components/layout'">
        <P>
          You're looking at it: this showcase uses it. It's an admin shell with a fixed sidebar of <code>NavLink</code>s (the active one is highlighted automatically)
          and a scrollable main area. Use it as a <strong>layout route</strong> and it renders <code>{'<Outlet />'}</code>, or pass <code>children</code>.
        </P>
        <Code>{`
          const AdminShell = () => {
            const { logout } = useAuth()
            return (
              <SidebarLayout
                brand={<h1 className="text-lg font-black">App</h1>}
                items={[
                  { label: 'Dashboard', to: '/admin', icon: DashboardSquare01Icon, end: true },  // end: exact match for index
                  { label: 'Users', to: '/admin/users', icon: UserIcon },
                ]}
                bottomItems={[{ label: 'Settings', to: '/admin/settings', icon: Settings01Icon }]}
                footer={<SidebarButton label="Logout" icon={Logout01Icon} onClick={logout} />}
              />
            )
          }

          <Route path="/admin" element={<AdminShell />}>
            <Route index element={<Dashboard />} />
            <Route path="users" element={<Users />} />
          </Route>
        `}</Code>
        <Props rows={[
          ['brand', 'ReactNode', '', 'Top of the sidebar'],
          ['items', 'SidebarNavItem[]', '', '{ label, to, icon, end? }'],
          ['bottomItems', 'SidebarNavItem[]', '[]', 'Links pinned above the footer (settings…)'],
          ['footer', 'ReactNode', '', 'Usually <SidebarButton>s (logout, refresh, theme toggle)'],
          ['children', 'ReactNode', '<Outlet />', 'Main area content when not used as a layout route'],
        ]} />
        <P>There's no mobile version (no drawer). For a phone-first app use PhoneFrame + MobileNav instead. The sidebar is fixed at <code>w-56</code> and the whole shell is capped at <code>max-w-360</code>.</P>
      </DocSection>

      <DocSection id="require-auth" title="RequireAuth" importLine="import { RequireAuth } from '@/components/layout'">
        <P>
          A layout-route guard. Without a session it redirects to <code>redirectTo</code> and puts the original location in <code>state.from</code>, so the login page can send the user back.
          With <code>roles</code>, the user needs at least one of them, otherwise they go to <code>forbiddenTo</code>.
          The live demo is on <Link className="underline" to={`${BASE}/auth#auth-context`}>Auth & API</Link>.
        </P>
        <Code>{`
          <Route element={<RequireAuth />}>                                   {/* any logged-in user */}
            <Route path="/admin" element={<AdminShell />}>
              <Route index element={<Dashboard />} />
              <Route element={<RequireAuth roles={['super_admin']} forbiddenTo="/admin" />}>
                <Route path="tenants" element={<Tenants />} />                {/* super_admin only */}
              </Route>
            </Route>
          </Route>
        `}</Code>
        <Props rows={[
          ['roles', 'string[]', '', 'Needs at least one (from the JWT role claim)'],
          ['redirectTo', 'string', "'/login'", 'Where unauthenticated users go'],
          ['forbiddenTo', 'string', "'/'", 'Where users without the role go'],
        ]} />
      </DocSection>
    </DocPage>
  )
}

export default LayoutPage
