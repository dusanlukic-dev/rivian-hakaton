import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { HugeiconsIcon } from '@hugeicons/react'
import { Copy01Icon, Tick02Icon } from '@hugeicons/core-free-icons'
import { cn } from '@/lib/utils'

/** Strips the leading newline and shared indentation from a template literal */
function dedent(code: string) {
  const lines = code.replace(/^\n/, '').replace(/\s+$/, '').split('\n')
  const indent = Math.min(...lines.filter((l) => l.trim()).map((l) => l.match(/^ */)![0].length))
  return lines.map((l) => l.slice(indent)).join('\n')
}

export const DocPage = ({ title, intro, toc, children }: {
  title: string
  intro?: ReactNode
  /** [id, label] pairs for the "On this page" links */
  toc?: [string, string][]
  children: ReactNode
}) => {
  // The browser tries to jump to #hash before this lazily-loaded page exists, so do it once mounted
  const { hash } = useLocation()
  useEffect(() => {
    if (hash) document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView()
  }, [hash])

  return (
  <div className="mx-auto flex max-w-4xl flex-col gap-12 p-6 pb-32">
    <header className="flex flex-col gap-3">
      <h1 className="text-2xl font-black tracking-tight">{title}</h1>
      {intro && (
        <div className="max-w-2xl text-sm text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:font-mono [&_code]:text-[0.85em] [&_code]:text-foreground">
          {intro}
        </div>
      )}
      {toc && (
        <nav className="flex flex-wrap gap-1.5 pt-1">
          {toc.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="rounded-full border px-2.5 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
              {label}
            </a>
          ))}
        </nav>
      )}
    </header>
    {children}
  </div>
  )
}

export const DocSection = ({ id, title, importLine, children }: {
  id: string
  title: string
  /** e.g. `import { Button } from '@/components/ui/button'` */
  importLine?: string
  children: ReactNode
}) => (
  <section id={id} className="flex scroll-mt-6 flex-col gap-4">
    <div className="flex flex-col gap-2 border-b pb-2">
      <h2 className="text-lg font-bold">{title}</h2>
      {importLine && <code className="w-fit rounded bg-muted px-2 py-1 font-mono text-[11px] text-muted-foreground">{importLine}</code>}
    </div>
    {children}
  </section>
)

export const P = ({ children }: { children: ReactNode }) => (
  <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:font-mono [&_code]:text-[0.85em] [&_code]:text-foreground">
    {children}
  </p>
)

/** Bordered box the live example renders in */
export const Demo = ({ children, className, label = 'Live' }: { children: ReactNode; className?: string; label?: string }) => (
  <div className="relative rounded-lg border bg-background">
    <span className="absolute -top-2 left-3 bg-background px-1 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">{label}</span>
    <div className={cn('flex flex-wrap items-center gap-3 p-5', className)}>{children}</div>
  </div>
)

export const Code = ({ children, title }: { children: string; title?: string }) => {
  const [copied, setCopied] = useState(false)
  const code = dedent(children)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error('Clipboard not available')
    }
  }

  return (
    <div className="group relative overflow-hidden rounded-lg border bg-muted/40">
      {title && <div className="border-b px-4 py-1.5 font-mono text-[11px] text-muted-foreground">{title}</div>}
      <button
        type="button"
        onClick={copy}
        title="Copy"
        className="absolute top-2 right-2 rounded-md border bg-background p-1.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-foreground focus:opacity-100"
      >
        <HugeiconsIcon icon={copied ? Tick02Icon : Copy01Icon} strokeWidth={1.8} className="size-3.5" />
      </button>
      <pre className="no-scrollbar overflow-x-auto p-4 font-mono text-xs leading-relaxed"><code>{code}</code></pre>
    </div>
  )
}

/** rows: [name, type, default, description] */
export const Props = ({ rows }: { rows: [string, string, string, string][] }) => (
  <div className="overflow-x-auto rounded-lg border">
    <table className="w-full text-xs">
      <thead>
        <tr className="border-b bg-muted/40 text-left text-[11px] tracking-wider text-muted-foreground uppercase">
          <th className="px-3 py-2 font-semibold">Prop</th>
          <th className="px-3 py-2 font-semibold">Type</th>
          <th className="px-3 py-2 font-semibold">Default</th>
          <th className="px-3 py-2 font-semibold">Description</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([name, type, def, desc]) => (
          <tr key={name} className="border-b last:border-0 align-top">
            <td className="px-3 py-2 font-mono font-medium whitespace-nowrap">{name}</td>
            <td className="px-3 py-2 font-mono text-muted-foreground">{type}</td>
            <td className="px-3 py-2 font-mono text-muted-foreground">{def || '—'}</td>
            <td className="px-3 py-2 text-muted-foreground">{desc}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)

/** Small key/value readout used by the live demos */
export const Readout = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="flex items-baseline gap-2 text-xs">
    <span className="text-muted-foreground">{label}</span>
    <span className="font-mono font-medium">{children}</span>
  </div>
)
