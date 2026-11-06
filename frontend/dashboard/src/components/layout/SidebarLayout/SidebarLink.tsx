import { NavLink } from 'react-router-dom'
import { HugeiconsIcon, type IconSvgElement } from '@hugeicons/react'
import { sidebarItemClass } from './sidebarItemClass'

export type SidebarNavItem = {
  label: string
  to: string
  icon: IconSvgElement
  /** Only active on an exact path match (use for index routes) */
  end?: boolean
}

const SidebarLink = ({ item }: { item: SidebarNavItem }) => (
  <NavLink to={item.to} end={item.end} className={({ isActive }) => sidebarItemClass(isActive)}>
    <HugeiconsIcon icon={item.icon} strokeWidth={1.5} className="size-4 shrink-0" />
    <span>{item.label}</span>
  </NavLink>
)

export default SidebarLink
