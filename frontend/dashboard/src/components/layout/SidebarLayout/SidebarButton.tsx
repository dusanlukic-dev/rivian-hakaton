import { HugeiconsIcon, type IconSvgElement } from '@hugeicons/react'
import { sidebarItemClass } from './sidebarItemClass'

type SidebarButtonProps = {
  label: string
  icon: IconSvgElement
  onClick: () => void
}

/** Action styled like a nav item — logout, refresh, etc. Pass it in `footer`. */
const SidebarButton = ({ label, icon, onClick }: SidebarButtonProps) => (
  <button type="button" onClick={onClick} className={sidebarItemClass()}>
    <HugeiconsIcon icon={icon} strokeWidth={1.5} className="size-4 shrink-0" />
    <span>{label}</span>
  </button>
)

export default SidebarButton
