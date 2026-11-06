import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { createColumnHelper } from '@tanstack/react-table'
import { toast } from 'sonner'
import { BackButton, DataTable, Modal, Onboarding, QrScanner, Section, SplashScreen, type OnboardingStep } from '@/components/shared'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { BASE } from '../base'
import { Code, Demo, DocPage, DocSection, P, Props, Readout } from '../_kit/Doc'

type Member = { id: number; name: string; role: string; active: boolean }

const members: Member[] = [
  { id: 1, name: 'Ana Petrović', role: 'Frontend', active: true },
  { id: 2, name: 'Marko Jovanović', role: 'Backend', active: true },
  { id: 3, name: 'Jelena Nikolić', role: 'Design', active: false },
  { id: 4, name: 'Luka Ilić', role: 'Pitch', active: true },
]

const col = createColumnHelper<Member>()
const columns = [
  col.accessor('name', { header: 'Name', cell: (info) => <span className="font-medium">{info.getValue()}</span> }),
  col.accessor('role', { header: 'Role' }),
  col.accessor('active', {
    header: 'Status',
    cell: (info) => info.getValue()
      ? <Badge className="border-green-500/20 bg-green-500/10 text-green-600">Active</Badge>
      : <Badge variant="secondary">Away</Badge>,
  }),
]

const steps: OnboardingStep[] = [
  { title: 'Zauzmi svoje mesto u hodu.', subtitle: 'Uzmi digitalni tiket dok si na kafi — red čeka tebe, a ne ti njega.' },
  { title: 'Nađi filijalu. Uzmi tiket.', subtitle: 'Rezerviši mesto pre nego što izađeš iz kuće.' },
  { title: 'Pametno čekanje.', subtitle: 'Prati status reda uživo i dođi tačno kad si na redu.' },
]

type TableState = 'data' | 'loading' | 'error' | 'empty'

const ComponentsPage = () => {
  const [tableState, setTableState] = useState<TableState>('data')
  const [scannerOpen, setScannerOpen] = useState(false)
  const [scanned, setScanned] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [onboardingKey, setOnboardingKey] = useState(0)
  const [splashKey, setSplashKey] = useState(0)

  return (
    <DocPage
      title="Components"
      intro={<>Bigger reusable pieces from <code>@/components/shared</code> (also re-exported from <code>@/components</code>). Unused ones are tree-shaken (see <code>"sideEffects"</code> in package.json), so importing from the barrel costs nothing.</>}
      toc={[
        ['login-form', 'LoginForm'], ['data-table', 'DataTable'], ['qr-scanner', 'QrScanner'], ['modal', 'Modal'],
        ['onboarding', 'Onboarding'], ['splash', 'SplashScreen'], ['section', 'Section'], ['back-button', 'BackButton'],
      ]}
    >
      <DocSection id="login-form" title="LoginForm" importLine="import { LoginForm, type LoginValues } from '@/components/shared'">
        <P>
          A centered username + password card with zod validation through react-hook-form. The button shows a loading state while submitting.
          If <code>onSubmit</code> throws, <code>errorMessage</code> appears under the fields. It's full-screen (<code>fixed inset-0</code>), so the demo opens on its own page.
          <code>src/pages/LoginPage/</code> shows the real wiring.
        </P>
        <Demo>
          <Button asChild><Link to={`${BASE}/demo/login`}>Open login demo →</Link></Button>
          <span className="text-xs text-muted-foreground">Password <code className="font-mono">demo</code> logs in (fake JWT); anything else shows the error state</span>
        </Demo>
        <Code>{`
          const { login } = useAuth()

          <LoginForm
            brand={<h1 className="text-3xl font-black">App</h1>}
            onSubmit={async ({ username, password }) => {
              const { data } = await api.post<{ token: string }>('/api/auth/login', { username, password })
              login(data.token)          // throwing (e.g. axios 401) shows errorMessage
            }}
          />
        `}</Code>
        <Props rows={[
          ['onSubmit', '(values: LoginValues) => Promise<void>', '', 'Throw to show the error message'],
          ['brand', 'ReactNode', '', 'Logo above the card'],
          ['title', 'string', "'Prijava'", 'Card title'],
          ['description', 'string', "'Unesite vaše kredencijale.'", 'Card subtitle'],
          ['errorMessage', 'string', "'Prijava nije uspela…'", 'Shown when onSubmit throws'],
        ]} />
        <P>Need different fields? Copy the file. The pattern of zod schema → <code>useForm({'{'} resolver: zodResolver(schema) {'}'})</code> → <code>register</code> → <code>errors.x.message</code> is the part to reuse.</P>
      </DocSection>

      <DocSection id="data-table" title="DataTable" importLine="import { DataTable } from '@/components/shared'  ·  import { createColumnHelper } from '@tanstack/react-table'">
        <P>A TanStack Table with the loading, error and empty states built in, plus striped rows. Pass <code>onRowClick</code> to make rows clickable.</P>
        <Demo className="flex-col items-stretch">
          <div className="flex flex-wrap gap-1.5">
            {(['data', 'loading', 'error', 'empty'] as TableState[]).map((s) => (
              <Button key={s} size="sm" variant={tableState === s ? 'default' : 'outline'} onClick={() => setTableState(s)}>{s}</Button>
            ))}
          </div>
          <DataTable
            data={tableState === 'empty' ? [] : members}
            columns={columns}
            isLoading={tableState === 'loading'}
            error={tableState === 'error' ? 'Greška pri učitavanju.' : null}
            onRowClick={(m) => toast(`Clicked ${m.name}`)}
          />
        </Demo>
        <Code>{`
          type Member = { id: number; name: string; active: boolean }
          const col = createColumnHelper<Member>()   // define outside the component (stable)
          const columns = [
            col.accessor('name', { header: 'Name' }),
            col.accessor('active', { header: 'Status', cell: (i) => i.getValue() ? <Badge>Active</Badge> : null }),
            col.display({ id: 'actions', cell: ({ row }) => <Button size="icon-sm" onClick={() => edit(row.original)}>…</Button> }),
          ]

          <DataTable data={members} columns={columns} isLoading={loading} error={error} onRowClick={(m) => navigate(\`/members/\${m.id}\`)} />
        `}</Code>
        <Props rows={[
          ['data', 'T[]', '', 'Rows'],
          ['columns', 'ColumnDef<T, any>[]', '', 'Build with createColumnHelper<T>()'],
          ['isLoading', 'boolean', '', 'Spinner instead of the table'],
          ['error', 'string | null', '', 'Red message instead of the table'],
          ['emptyMessage', 'ReactNode', "'Nema podataka.'", 'Shown when data is empty'],
          ['loadingMessage', 'ReactNode', "'Učitavanje...'", ''],
          ['onRowClick', '(row: T) => void', '', 'Adds pointer + hover to rows'],
        ]} />
        <P>Sorting and filtering aren't included. Add <code>getSortedRowModel()</code> / <code>getFilteredRowModel()</code> in the component if you need them.</P>
      </DocSection>

      <DocSection id="qr-scanner" title="QrScanner" importLine="import { QrScanner } from '@/components/shared'">
        <P>
          A camera QR scanner built on <code>html5-qrcode</code>. It prefers the back camera, shows a camera switcher when there's more than one, can scan from an image file,
          and resizes the scan box with its container. The camera only works on <strong>HTTPS or localhost</strong>, so test on a phone through an ngrok URL.
          It fills its parent (<code>h-full</code>), so give the parent a height.
        </P>
        <Demo className="flex-col items-start">
          {scannerOpen ? (
            <div className="h-[460px] w-full max-w-sm overflow-hidden rounded-xl border">
              <QrScanner onScan={(text) => { setScanned(text); toast.success(`Scanned: ${text}`) }} />
            </div>
          ) : (
            <Button onClick={() => setScannerOpen(true)}>Start scanner (asks for camera)</Button>
          )}
          {scannerOpen && <Button variant="outline" size="sm" onClick={() => setScannerOpen(false)}>Close scanner</Button>}
          <Readout label="last scan:">{scanned ?? '—'}</Readout>
        </Demo>
        <Code>{`
          <div className="h-[460px]">
            <QrScanner onScan={(text) => navigate(\`/ticket/\${text}\`)} />
          </div>
        `}</Code>
        <Props rows={[
          ['onScan', '(text: string) => void', '', 'Decoded QR content'],
          ['stopOnScan', 'boolean', 'true', 'Pause after the first read. Turn off for continuous scanning (onScan then fires every frame the code is visible)'],
          ['className', 'string', '', 'Root element classes'],
        ]} />
        <P>The camera is released on unmount, so just conditionally render it. Several scanners can be on a page at once because each gets a unique id via <code>useId</code>.</P>
      </DocSection>

      <DocSection id="modal" title="Modal" importLine="import { Modal } from '@/components/shared'  ·  import { AnimatePresence } from 'motion/react'">
        <P>
          A full-screen blurred overlay rendered into <code>{'<body>'}</code> through a portal. It locks page scroll and pads <code>#root</code> by the scrollbar width so nothing jumps sideways, and nested modals work.
          Position the content yourself through <code>className</code>. Wrap it in <code>AnimatePresence</code> to get a fade on exit.
          It has no Escape key handling and no focus trap. For a fully accessible dialog, run <code>npx shadcn add dialog</code>.
        </P>
        <Demo>
          <Button onClick={() => setModalOpen(true)}>Open modal</Button>
          <AnimatePresence>
            {modalOpen && (
              <Modal animateInitial className="flex items-center justify-center bg-black/30 p-4" onBackgroundClick={() => setModalOpen(false)}>
                <motion.div initial={{ scale: 0.95, y: 8 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 8 }}>
                  <Card className="w-80">
                    <CardHeader>
                      <CardTitle>Hello from a Modal</CardTitle>
                      <CardDescription>Click the blurred background or the button to close.</CardDescription>
                    </CardHeader>
                    <CardContent className="text-xs text-muted-foreground">The page behind can't scroll while this is open.</CardContent>
                    <CardFooter><Button className="w-full" onClick={() => setModalOpen(false)}>Close</Button></CardFooter>
                  </Card>
                </motion.div>
              </Modal>
            )}
          </AnimatePresence>
        </Demo>
        <Code>{`
          <AnimatePresence>
            {open && (
              <Modal animateInitial className="flex items-center justify-center bg-black/30" onBackgroundClick={() => setOpen(false)}>
                <Card>…</Card>
              </Modal>
            )}
          </AnimatePresence>
        `}</Code>
        <Props rows={[
          ['onBackgroundClick', '() => void', '', 'Clicks on the overlay itself (not its children)'],
          ['animateInitial', 'boolean', '', 'Fade in on mount'],
          ['className', 'string', '', 'Overlay classes: positioning, tint'],
          ['onAnimationComplete', '(def) => void', '', 'motion callback'],
        ]} />
      </DocSection>

      <DocSection id="onboarding" title="Onboarding" importLine="import { Onboarding, type OnboardingStep } from '@/components/shared'">
        <P>Intro screens with back, skip and next buttons and progress dots. Each step fades in. It fills its parent, which is usually a PhoneFrame.</P>
        <Demo className="flex-col items-start">
          <div className="h-[520px] w-80 overflow-hidden rounded-xl border">
            <Onboarding key={onboardingKey} steps={steps} onFinish={() => toast.success('onFinish() called')} />
          </div>
          <Button size="sm" variant="outline" onClick={() => setOnboardingKey((k) => k + 1)}>Restart</Button>
        </Demo>
        <Code>{`
          const steps: OnboardingStep[] = [
            { title: 'Welcome', subtitle: 'What the app does', image: '/onboarding-1.png' },
            { title: 'Step two', subtitle: '…' },
          ]
          <Onboarding steps={steps} onFinish={() => setStage('app')} labels={{ next: 'Next', finish: 'Start' }} />
        `}</Code>
        <Props rows={[
          ['steps', 'OnboardingStep[]', '', '{ title, subtitle?, image? } (image is a URL; put files in public/)'],
          ['onFinish', '() => void', '', 'Called by "finish" on the last step and by "skip"'],
          ['labels', '{ back?, skip?, next?, finish? }', 'Serbian', "Button texts ('Nazad', 'Preskoči', 'Dalje', 'Započni')"],
        ]} />
      </DocSection>

      <DocSection id="splash" title="SplashScreen" importLine="import { SplashScreen } from '@/components/shared'">
        <P>An app-launch screen: your logo scales and fades in, with bouncing dots underneath. Show it for a couple of seconds, then swap it out (see the PhoneFrame flow on the Layout page).</P>
        <Demo className="flex-col items-start">
          <div className="h-64 w-80 overflow-hidden rounded-xl border">
            <SplashScreen key={splashKey}><h1 className="text-4xl font-black"><span className="text-chart-3">e</span>App</h1></SplashScreen>
          </div>
          <Button size="sm" variant="outline" onClick={() => setSplashKey((k) => k + 1)}>Replay</Button>
        </Demo>
        <Code>{`
          <SplashScreen><img src="/logo.svg" className="h-16" /></SplashScreen>
        `}</Code>
      </DocSection>

      <DocSection id="section" title="Section" importLine="import { Section } from '@/components/shared'">
        <P>A <code>{'<section>'}</code> with Tailwind's <code>container</code> class and an optional <code>{'<h2>'}</code>, for landing pages. All normal section props pass through.</P>
        <Demo className="block">
          <Section heading="Section heading" isContainer={false} className="rounded-md bg-muted/40 p-4 text-sm [&>h2]:mb-1 [&>h2]:font-bold">
            Children go here.
          </Section>
        </Demo>
        <Code>{`
          <Section id="features" heading="Features" className="py-16">…</Section>
          <Section isContainer={false}>…full width…</Section>
        `}</Code>
      </DocSection>

      <DocSection id="back-button" title="BackButton" importLine="import { BackButton } from '@/components/shared'">
        <Demo>
          <BackButton />
          <BackButton to={`${BASE}/layout`} label="Layout page" />
        </Demo>
        <Code>{`
          <BackButton />                                  // navigate(-1), label 'Nazad'
          <BackButton to="/admin/users" label="Users" />   // fixed target
        `}</Code>
      </DocSection>
    </DocPage>
  )
}

export default ComponentsPage
