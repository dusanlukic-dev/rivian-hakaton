import type { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import SidebarLink, { type SidebarNavItem } from './SidebarLink'

type SidebarLayoutProps = {
  /** Logo / app name at the top */
  brand: ReactNode
  items: SidebarNavItem[]
  /** Links pinned to the bottom, above `footer` (e.g. settings) */
  bottomItems?: SidebarNavItem[]
  /** Anything below the bottom links — usually `<SidebarButton>`s */
  footer?: ReactNode
  /** Rendered instead of `<Outlet />` when not used as a layout route */
  children?: ReactNode
}

/** Admin-dashboard shell: fixed sidebar + scrollable main area. Use as a layout route. */
const SidebarLayout = ({ brand, items, bottomItems = [], footer, children }: SidebarLayoutProps) => {
  return (
    <div className="flex h-dvh bg-muted/30">
      <div className="mx-auto flex h-full w-full max-w-360 overflow-hidden border-x border-border bg-background shadow-sm">
        <aside className="flex h-full w-56 shrink-0 flex-col border-r border-border bg-background px-3 py-5">
          <div className="mb-6 px-3">{brand}</div>

          <nav className="flex flex-1 flex-col gap-0.5">
            {items.map((item) => (
              <SidebarLink key={item.to} item={item} />
            ))}
          </nav>

          {(bottomItems.length > 0 || footer) && (
            <nav className="flex flex-col gap-0.5 border-t border-border pt-4">
              {bottomItems.map((item) => (
                <SidebarLink key={item.to} item={item} />
              ))}
              {footer}
            </nav>
          )}
        </aside>

        <main className="no-scrollbar flex-1 overflow-x-hidden overflow-y-auto">
          {children ?? <Outlet />}
        </main>
      </div>
    </div>
  )
}

export default SidebarLayout
