import { createBrowserRouter, createRoutesFromElements, Route, RouterProvider } from 'react-router-dom'
import { DashboardSquare01Icon, Logout01Icon, Settings01Icon } from '@hugeicons/core-free-icons'
import { RequireAuth, SidebarButton, SidebarLayout } from '@/components/layout'
import { AuthProvider, useAuth } from '@/context/AuthContext'
import { CarScreen, ErrorPage, LoginPage, TripReportPage } from '@/pages'

// Example admin shell — replace items / pages with your own
const AdminShell = () => {
  const { logout } = useAuth()
  return (
    <SidebarLayout
      brand={<h1 className="text-lg font-black">App</h1>}
      items={[{ label: 'Dashboard', to: '/admin', icon: DashboardSquare01Icon, end: true }]}
      bottomItems={[{ label: 'Settings', to: '/admin/settings', icon: Settings01Icon }]}
      footer={<SidebarButton label="Logout" icon={Logout01Icon} onClick={logout} />}
    />
  )
}

const router = createBrowserRouter(
  createRoutesFromElements(
    <Route errorElement={<ErrorPage />}>
      <Route path='/' element={<CarScreen />} />
      <Route path='/trip/:id' element={<TripReportPage />} />
      <Route path='/login' element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route path='/admin' element={<AdminShell />}>
          <Route index element={<div className="p-6">Dashboard</div>} />
          <Route path='settings' element={<div className="p-6">Settings</div>} />
        </Route>
      </Route>

      <Route path='/usage-examples/*' lazy={() => import('@/showcase')} hydrateFallbackElement={<></>} /> {/* dev showcase — delete this line to remove */}
    </Route>
  )
)

const App = () => (
  <AuthProvider>
    <RouterProvider router={router} />
  </AuthProvider>
)

export default App
