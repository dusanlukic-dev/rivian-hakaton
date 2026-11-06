/**
 * Living docs for everything in src/ — lazy-loaded by ONE line in App.tsx.
 * To remove from the product: delete that line (and optionally this folder). Nothing else imports it.
 */
import { Route, Routes, useNavigate } from 'react-router-dom'
import { useTheme } from 'next-themes'
import {
  Alert02Icon,
  ArrowLeft01Icon,
  BookOpen01Icon,
  CodeIcon,
  Key01Icon,
  LayoutLeftIcon,
  Moon02Icon,
  PaintBoardIcon,
  PuzzleIcon,
  Sun03Icon,
  Wrench01Icon,
} from '@hugeicons/core-free-icons'
import { SidebarButton, SidebarLayout, type SidebarNavItem } from '@/components/layout'
import { BASE } from './base'
import Overview from './pages/Overview'
import UiPage from './pages/UiPage'
import LayoutPage from './pages/LayoutPage'
import ComponentsPage from './pages/ComponentsPage'
import HooksPage from './pages/HooksPage'
import AuthApiPage from './pages/AuthApiPage'
import UtilsPage from './pages/UtilsPage'
import ErrorsPage from './pages/ErrorsPage'
import PhoneDemo from './demos/PhoneDemo'
import LoginDemo from './demos/LoginDemo'
import CrashDemo from './demos/CrashDemo'

const items: SidebarNavItem[] = [
  { label: 'Overview', to: BASE, icon: BookOpen01Icon, end: true },
  { label: 'UI (shadcn)', to: `${BASE}/ui`, icon: PaintBoardIcon },
  { label: 'Layout', to: `${BASE}/layout`, icon: LayoutLeftIcon },
  { label: 'Components', to: `${BASE}/components`, icon: PuzzleIcon },
  { label: 'Hooks', to: `${BASE}/hooks`, icon: CodeIcon },
  { label: 'Auth & API', to: `${BASE}/auth`, icon: Key01Icon },
  { label: 'Utils & SCSS', to: `${BASE}/utils`, icon: Wrench01Icon },
  { label: 'Error pages', to: `${BASE}/errors`, icon: Alert02Icon },
]

const Shell = () => {
  const navigate = useNavigate()
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

  return (
    <SidebarLayout
      brand={
        <>
          <h1 className="text-lg font-black">Showcase</h1>
          <p className="text-xs text-muted-foreground">Every shared thing, live</p>
        </>
      }
      items={items}
      footer={
        <>
          <SidebarButton label={isDark ? 'Light mode' : 'Dark mode'} icon={isDark ? Sun03Icon : Moon02Icon} onClick={() => setTheme(isDark ? 'light' : 'dark')} />
          <SidebarButton label="Back to app" icon={ArrowLeft01Icon} onClick={() => navigate('/')} />
        </>
      }
    />
  )
}

const ShowcaseApp = () => (
  <Routes>
    {/* Full-screen demos — outside the sidebar because these components cover the viewport */}
    <Route path="demo/phone" element={<PhoneDemo />} />
    <Route path="demo/login" element={<LoginDemo />} />
    <Route path="demo/crash" element={<CrashDemo />} />

    <Route element={<Shell />}>
      <Route index element={<Overview />} />
      <Route path="ui" element={<UiPage />} />
      <Route path="layout" element={<LayoutPage />} />
      <Route path="components" element={<ComponentsPage />} />
      <Route path="hooks" element={<HooksPage />} />
      <Route path="auth" element={<AuthApiPage />} />
      <Route path="utils" element={<UtilsPage />} />
      <Route path="errors" element={<ErrorsPage />} />
      <Route path="*" element={<Overview />} />
    </Route>
  </Routes>
)

// React Router's `lazy` reads route properties off the module — `Component` is the element to render
export { ShowcaseApp as Component }
