import type { ReactNode } from 'react'

type PhoneFrameProps = {
  children?: ReactNode
}

/**
 * Renders the app inside an iPhone-style frame on desktop, for demoing a mobile app on a laptop/projector.
 * On real phones (below `sm`) the frame disappears and the app is full-screen.
 */
const PhoneFrame = ({ children }: PhoneFrameProps) => {
  return (
    <div className="fixed inset-0 flex items-center justify-center overflow-hidden bg-muted/30 p-4 max-sm:p-0">
      <div className="relative flex h-full max-h-[844px] aspect-[390/844] shrink-0 flex-col overflow-hidden rounded-[52px] border-[8px] border-zinc-950 bg-background shadow-2xl ring-1 ring-border/20 dark:border-zinc-900 max-sm:aspect-auto max-sm:max-h-none max-sm:w-full max-sm:rounded-none max-sm:border-0 max-sm:shadow-none max-sm:ring-0">

        {/* Dynamic Island */}
        <div className="pointer-events-none absolute inset-x-0 top-0 z-[9999] flex justify-center max-sm:hidden">
          <div className="mt-[10px] h-[30px] w-[95px] rounded-full bg-zinc-950 shadow-sm" />
        </div>

        <div id="phone-container" className="no-scrollbar relative h-full w-full flex-1 overflow-x-hidden overflow-y-auto bg-background">
          {/* Top padding keeps content clear of the island */}
          <div className="flex h-full flex-col pt-8 max-sm:pt-0">
            {children}
          </div>
        </div>

        {/* Home indicator */}
        <div className="pointer-events-none absolute inset-x-0 bottom-2 z-[9999] flex justify-center max-sm:hidden">
          <div className="h-[5px] w-[134px] rounded-full bg-foreground/20" />
        </div>
      </div>
    </div>
  )
}

export default PhoneFrame
