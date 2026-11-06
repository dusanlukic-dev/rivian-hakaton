import { cn } from '@/lib/utils'

interface WordmarkProps {
  /** The app name (config/brand.json). "Vigil" gets the logo's lens */
  name: string
  /** Lens colour: Vigil's accent by default; the live state colour while a trip runs */
  lens?: string
  className?: string
}

/**
 * Vigil wordmark: lowercase Noto Sans Mono 700, tracking −0.02em. In "vigil" the dot of the last i is a small ring,
 * the camera lens that watches. Other names get the same type without the lens
 */
const Wordmark = ({ name, lens = 'var(--brand-accent)', className }: WordmarkProps) => {
  const text = name.toLowerCase()
  const i = text === 'vigil' ? text.lastIndexOf('i') : -1
  return (
    <span className={cn('font-bold tracking-[-0.02em] whitespace-nowrap', className)}>
      <span className="sr-only">{name}</span>
      <span aria-hidden>
        {i < 0 ? (
          text
        ) : (
          <>
            {text.slice(0, i)}
            <span className="relative inline-block">
              {'ı'}
              <span
                className="absolute top-[0.1em] left-1/2 size-[0.27em] -translate-x-1/2 rounded-full border-[0.085em] transition-colors duration-300"
                style={{ borderColor: lens }}
              />
            </span>
            {text.slice(i + 1)}
          </>
        )}
      </span>
    </span>
  )
}

export default Wordmark
