import { Link } from 'react-router-dom'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { BASE } from '../base'
import { Code, DocPage, DocSection, P } from '../_kit/Doc'

const pages: [string, string, string][] = [
  ['ui', 'UI (shadcn)', 'Button, Badge, Card, inputs, Checkbox, Switch, Select, DropdownMenu, Skeleton, toasts'],
  ['layout', 'Layout', 'PhoneFrame, MobileNav, SidebarLayout + SidebarButton, RequireAuth'],
  ['components', 'Components', 'LoginForm, DataTable, QrScanner, Modal, Onboarding, SplashScreen, Section, BackButton'],
  ['hooks', 'Hooks', 'useDebounce, useVisibility, useLocalStorage, useSignalR'],
  ['auth', 'Auth & API', 'AuthProvider / useAuth, axios client, JWT helpers'],
  ['utils', 'Utils & SCSS', 'cn, round / adjust, SVG path parser (morph demo), documentManager, SCSS functions + media queries'],
  ['errors', 'Error pages', 'ErrorPage: 404 and generic error'],
]

const Overview = () => (
  <DocPage
    title="Every shared component and thing"
    intro={<>Live docs for everything reusable in <code className="font-mono">src/</code>. Every page shows the import, the props, a working example and copy-paste code.</>}
  >
    <div className="grid gap-3 sm:grid-cols-2">
      {pages.map(([path, title, desc]) => (
        <Link key={path} to={`${BASE}/${path}`}>
          <Card className="h-full transition-colors hover:bg-muted/40">
            <CardHeader>
              <CardTitle>{title}</CardTitle>
              <CardDescription>{desc}</CardDescription>
            </CardHeader>
          </Card>
        </Link>
      ))}
    </div>

    <DocSection id="remove" title="Removing this showcase from the product">
      <P>
        The whole showcase hangs off <strong>one line</strong> in <code>src/App.tsx</code>. Delete it and the showcase is gone.
        It's lazy-loaded, so even while it's there it ships as a separate chunk that only downloads when someone opens this URL.
        You can then delete <code>src/showcase/</code> too, though nothing breaks if you leave it.
      </P>
      <Code title="src/App.tsx">{`
        <Route path='/usage-examples/*' lazy={() => import('@/showcase')} hydrateFallbackElement={<></>} /> {/* dev showcase — delete this line to remove */}
      `}</Code>
      <P>
        To keep it in dev but leave it out of production builds, wrap that line in <code>{'{import.meta.env.DEV && ( … )}'}</code>.
        If you change the path, update <code>BASE</code> in <code>src/showcase/base.ts</code> as well.
      </P>
    </DocSection>

    <DocSection id="conventions" title="Conventions">
      <P>
        Imports always use the <code>@/</code> alias, which points at <code>src/</code>. Icons come only from <strong>Hugeicons</strong>,
        never heroicons or bootstrap-icons. Animations use <code>motion/react</code>, not <code>framer-motion</code>. Class names are merged with <code>cn()</code>.
      </P>
      <Code>{`
        import { HugeiconsIcon } from '@hugeicons/react'
        import { Home01Icon } from '@hugeicons/core-free-icons'   // browse: https://hugeicons.com/icons
        import { motion, AnimatePresence } from 'motion/react'
        import { cn } from '@/lib/utils'

        <HugeiconsIcon icon={Home01Icon} strokeWidth={1.5} className="size-4" />
      `}</Code>
      <P>
        More shadcn components: <code>npx shadcn@latest add dialog table tabs tooltip sheet</code>. They land in <code>src/components/ui/</code>.
      </P>
      <P>
        Every component has its own folder, even when it's a single file. The folder holds the component, its <code>.scss</code> if it has one, any child components only it uses,
        and an <code>index.ts</code> that exports the public API. Each level re-exports the one below it, so you can import from whichever level is shortest.{' '}
        <code>components/ui/</code> is the exception: it stays flat because the shadcn CLI writes files there.
      </P>
      <Code>{`
        components/
          index.ts                 export * from './layout'; export * from './shared'
          shared/
            index.ts               export * from './QrScanner'  …
            QrScanner/
              index.ts             export { default as QrScanner } from './QrScanner'
              QrScanner.tsx
              QrScanner.scss
              QrBoxOutline.tsx     private child, not exported

        import { DataTable, PhoneFrame } from '@/components'      // same as '@/components/shared' / '@/components/layout'
        import { ErrorPage, LoginPage } from '@/pages'
        import { AuthProvider, useAuth } from '@/context'          // or '@/context/AuthContext'
      `}</Code>
    </DocSection>

    <DocSection id="start" title="Starting a new project from this">
      <Code>{`
        cp .env.example .env     # VITE_API_URL=http://localhost:5000 (or your ngrok URL)
        npm install
        npm run dev              # /api and /hubs are proxied to VITE_API_URL
        npm run build            # tsc + vite build → dist/ (vercel.json already has the SPA rewrite)
      `}</Code>
    </DocSection>
  </DocPage>
)

export default Overview
