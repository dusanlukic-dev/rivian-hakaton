import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { adjust, round } from '@/utils/math/math'
import { encodePath, parsePath } from '@/utils/parsers/pathParser'
import { documentManager, type Lock } from '@/utils/dom/documentManager'
import { Button } from '@/components/ui/button'
import { Code, Demo, DocPage, DocSection, P, Readout } from '../_kit/Doc'
import '../showcase.scss'

type Points = ReturnType<typeof parsePath>

// Same structure (M + 4×C) so the points line up one-to-one
const CIRCLE = parsePath('M50 10 C72 10 90 28 90 50 C90 72 72 90 50 90 C28 90 10 72 10 50 C10 28 28 10 50 10 Z')
const STAR = parsePath('M50 4 C56 44 56 44 96 50 C56 56 56 56 50 96 C44 56 44 56 4 50 C44 44 44 44 50 4 Z')

const lerp = (a: number, b: number, t: number) => adjust(t, 0, 1, a, b)
const lerpOpt = (a: number | undefined, b: number | undefined, t: number) =>
  a === undefined || b === undefined ? undefined : lerp(a, b, t)

function morph(a: Points, b: Points, t: number): Points {
  return a.map((p, i) => {
    const q = b[i]
    return {
      x: lerp(p.x, q.x, t), y: lerp(p.y, q.y, t),
      xs: lerpOpt(p.xs, q.xs, t), ys: lerpOpt(p.ys, q.ys, t),
      xe: lerpOpt(p.xe, q.xe, t), ye: lerpOpt(p.ye, q.ye, t),
    }
  })
}

const ScrollLockDemo = () => {
  const [locks, setLocks] = useState<Lock[]>([])
  const [bodyOverflow, setBodyOverflow] = useState(() => document.body.style.overflowY || 'unset')
  // Mirror for the unmount cleanup, so leaving the page never leaves the body locked
  const locksRef = useRef<Lock[]>([])
  useEffect(() => () => locksRef.current.forEach((l) => l.release()), [])

  const update = (next: Lock[]) => {
    locksRef.current = next
    setLocks(next)
    setBodyOverflow(document.body.style.overflowY || 'unset')
  }

  const inertFor3s = () => {
    documentManager.enableInertRoot()
    toast('#root is inert for 3 s. Try clicking anything')
    setTimeout(() => documentManager.disableInertRoot(), 3000)
  }

  return (
    <Demo className="flex-col items-start">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => update([...locks, documentManager.lockScroll('hidden')])}>lockScroll('hidden')</Button>
        <Button size="sm" variant="outline" onClick={() => update([...locks, documentManager.lockScroll('clip')])}>lockScroll('clip')</Button>
        <Button size="sm" variant="outline" onClick={inertFor3s}>enableInertRoot() for 3 s</Button>
      </div>
      <Readout label="body overflow-y:">{bodyOverflow}</Readout>
      <div className="flex flex-wrap gap-1.5">
        {locks.map((lock, i) => (
          <Button key={i} size="xs" variant="secondary" onClick={() => { lock.release(); update(locks.filter((l) => l !== lock)) }}>
            release #{i + 1} ({lock.value})
          </Button>
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground">
        The first lock's value wins. Releasing it hands over to the next one, and releasing the last restores the body.
        (This page scrolls inside the sidebar's main area, so a body lock isn't visible here.)
      </p>
    </Demo>
  )
}

const UtilsPage = () => {
  const [t, setT] = useState(0)
  const [value, setValue] = useState(25)
  const d = encodePath(morph(CIRCLE, STAR, t))

  return (
    <DocPage
      title="Utils & SCSS"
      intro="Small helpers. All of them are plain functions, so you can import them anywhere."
      toc={[['cn', 'cn'], ['math', 'round / adjust'], ['path', 'pathParser'], ['document-manager', 'documentManager'], ['scss', 'SCSS']]}
    >
      <DocSection id="cn" title="cn()" importLine="import { cn } from '@/lib/utils'">
        <P>Joins class names (clsx) and resolves Tailwind conflicts (tailwind-merge), so the last one wins. Use it for every <code>className</code> prop you merge.</P>
        <Code>{`
          cn('px-2 py-1', isActive && 'bg-primary', className)   // falsy values are dropped
          cn('p-4', 'p-2')                                       // → 'p-2'
        `}</Code>
      </DocSection>

      <DocSection id="math" title="round / adjust" importLine="import { round, adjust } from '@/utils/math/math'">
        <P><code>adjust</code> remaps a value from one range to another; it's linear interpolation, and the ranges can be reversed. <code>round</code> rounds to a precision (default 3). Typical uses: a scroll position → opacity, or a slider → rotation.</P>
        <Demo className="flex-col items-start">
          <input type="range" min={0} max={100} value={value} onChange={(e) => setValue(Number(e.target.value))} className="w-64 accent-primary" />
          <Readout label="value:">{value}</Readout>
          <Readout label="adjust(value, 0, 100, 0, 1):">{adjust(value, 0, 100, 0, 1)}</Readout>
          <Readout label="adjust(value, 0, 100, 100, 0):">{adjust(value, 0, 100, 100, 0)}</Readout>
          <Readout label="adjust(value, 0, 100, -180, 180) → deg:">{adjust(value, 0, 100, -180, 180)}</Readout>
          <Readout label="round(Math.PI * value, 2):">{round(Math.PI * value, 2)}</Readout>
        </Demo>
        <Code>{`
          adjust(10, 0, 100, 100, 0)            // → 90
          const opacity = adjust(scrollY, 0, 400, 1, 0)
          round(3.14159, 2)                     // → 3.14
        `}</Code>
      </DocSection>

      <DocSection id="path" title="pathParser — parsePath / encodePath" importLine="import { parsePath, encodePath } from '@/utils/parsers/pathParser'">
        <P>
          Converts an SVG <code>d</code> string into points (with Bézier control handles) and back. That's the basis of shape morphing: parse two paths with the same structure, interpolate every number, and encode the result.
          It supports the absolute commands <code>M L H V C Z</code>. Relative (lowercase) commands throw, so export from Figma with absolute coordinates.
        </P>
        <Demo>
          <svg viewBox="0 0 100 100" className="size-40 text-primary">
            <path d={d} fill="currentColor" />
          </svg>
          <div className="flex flex-col gap-2">
            <input type="range" min={0} max={1} step={0.01} value={t} onChange={(e) => setT(Number(e.target.value))} className="w-56 accent-primary" />
            <Readout label="t:">{t.toFixed(2)}</Readout>
            <code className="max-w-xs font-mono text-[10px] break-all text-muted-foreground">{d}</code>
          </div>
        </Demo>
        <Code>{`
          const A = parsePath(circleD), B = parsePath(starD)   // same commands, same count
          const lerp = (a: number, b: number, t: number) => adjust(t, 0, 1, a, b)
          const d = encodePath(A.map((p, i) => ({
            x: lerp(p.x, B[i].x, t), y: lerp(p.y, B[i].y, t),
            xs: …, ys: …, xe: …, ye: …,   // same for the control handles when both exist
          })))

          <path d={d} />   // drive t from a slider, scroll position, or motion's useMotionValue
        `}</Code>
      </DocSection>

      <DocSection id="document-manager" title="documentManager" importLine="import { documentManager } from '@/utils/dom/documentManager'">
        <P>
          Body scroll locks that stack, so several modals or drawers can each hold one and release in any order. Plus toggling <code>inert</code> on <code>#root</code>,
          which makes everything behind a portal unclickable and unfocusable. <code>Modal</code> already uses the scroll lock.
        </P>
        <ScrollLockDemo />
        <Code>{`
          useLayoutEffect(() => {
            const lock = documentManager.lockScroll('hidden')
            return () => lock.release()
          }, [])
        `}</Code>
      </DocSection>

      <DocSection id="scss" title="SCSS: mapped() + media queries" importLine="@use '@/…' won't resolve in Sass — use a relative path: @use '../utils/css/functions';">
        <P>
          <code>mapped($min, $max)</code> produces a value that scales fluidly from the 402px Figma phone frame to the 1440px desktop frame, and is clamped outside that range.
          It's the fastest way to turn two Figma sizes into one responsive rule. The media query variables have names like <code>$phone</code>, <code>$tablet</code> and <code>$desktop</code>.
          <strong> Resize the window</strong> to see both change:
        </P>
        <Demo className="flex-col items-start">
          <span className="showcase-fluid">Fluid heading</span>
          <span className="showcase-mq font-mono text-xs text-muted-foreground" />
        </Demo>
        <Code title="src/showcase/showcase.scss">{`
          @use '../utils/css/functions';
          @use '../utils/css/mediaqueries' as mq;

          .showcase-fluid {
            font-size: functions.mapped(14px, 40px);            // 14px at ≤402px → 40px at ≥1440px
            padding: functions.mapped(16px, 64px, 375px, 1280px); // custom viewport range
          }

          .card {
            @media #{mq.$phone} { padding: 8px; }               // max-width: 768px
            @media #{mq.$desktop} { padding: 24px; }            // min-width: 1201px
          }
        `}</Code>
        <P>For most things Tailwind's breakpoints (<code>sm: md: lg:</code>, <code>max-sm:</code>) are simpler. Reach for these SCSS helpers when you're writing a <code>.scss</code> file anyway.</P>
      </DocSection>
    </DocPage>
  )
}

export default UtilsPage
