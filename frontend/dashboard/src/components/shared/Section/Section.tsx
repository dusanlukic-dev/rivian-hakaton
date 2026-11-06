import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

type SectionProps = ComponentProps<'section'> & {
  heading?: string
  /** Adds Tailwind's `container` class. Default: true */
  isContainer?: boolean
}

const Section = ({ heading, isContainer = true, className, children, ...props }: SectionProps) => (
  <section className={cn(isContainer && 'container', className)} {...props}>
    {heading && <h2>{heading}</h2>}
    {children}
  </section>
)

export default Section
