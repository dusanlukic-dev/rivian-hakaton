import { cn } from '@/lib/utils'

/** Shared look of nav links and buttons in the sidebar */
export const sidebarItemClass = (isActive = false) =>
  cn(
    'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors select-none',
    isActive ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
  )
