import { HugeiconsIcon, type IconSvgElement } from '@hugeicons/react'
import { cn } from '@/lib/utils'

export type MobileNavItem<K extends string = string> = {
  key: K
  label: string
  icon: IconSvgElement
  /** Shows a dot on the icon, e.g. "you have an active ticket" */
  badge?: boolean
}

type MobileNavProps<K extends string> = {
  items: MobileNavItem<K>[]
  active: K
  onChange: (key: K) => void
  className?: string
}

/** Bottom tab bar. Sticks to the bottom of its scroll container. */
const MobileNav = <K extends string>({ items, active, onChange, className }: MobileNavProps<K>) => {
  return (
    <nav
      className={cn(
        'sticky bottom-0 z-[999] mt-auto flex w-full items-center justify-between border-t border-border/40 bg-background/85 px-6 pt-3 pb-8 backdrop-blur-2xl',
        className
      )}
    >
      {items.map((item) => {
        const isActive = item.key === active
        return (
          <button
            key={item.key}
            type="button"
            aria-current={isActive ? 'page' : undefined}
            onClick={() => onChange(item.key)}
            className={cn(
              'relative flex flex-col items-center gap-1 transition-colors focus:outline-none',
              isActive || item.badge ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            <HugeiconsIcon icon={item.icon} strokeWidth={isActive ? 2.2 : 1.5} className="size-6" />
            <span className={cn('text-[10px] tracking-tight', isActive || item.badge ? 'font-bold' : 'font-medium')}>
              {item.label}
            </span>
            {item.badge && (
              <span className="absolute top-0 right-2 size-2 rounded-full border border-background bg-chart-1" />
            )}
          </button>
        )
      })}
    </nav>
  )
}

export default MobileNav
