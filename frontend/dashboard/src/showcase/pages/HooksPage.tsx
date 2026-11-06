import { useState } from 'react'
import useDebounce from '@/hooks/useDebounce'
import useVisibility from '@/hooks/useVisibility'
import useLocalStorage from '@/hooks/useLocalStorage'
import { liveUrl, useLive, type LiveStatus } from '@/hooks/useLive'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Code, Demo, DocPage, DocSection, P, Props, Readout } from '../_kit/Doc'

const CounterCard = ({ name }: { name: string }) => {
  // Both cards use the same key → they stay in sync without sharing state or context
  const [count, setCount, reset] = useLocalStorage('showcase:counter', 0)
  return (
    <div className="flex flex-col gap-2 rounded-md border p-3">
      <span className="text-[11px] text-muted-foreground">{name}</span>
      <span className="font-mono text-2xl font-bold">{count}</span>
      <div className="flex gap-1.5">
        <Button size="sm" onClick={() => setCount((c) => c + 1)}>+1</Button>
        <Button size="sm" variant="ghost" onClick={reset}>reset</Button>
      </div>
    </div>
  )
}

const statusColor: Record<LiveStatus, string> = {
  idle: 'bg-muted text-muted-foreground',
  connecting: 'bg-yellow-500/15 text-yellow-700 dark:text-yellow-400',
  reconnecting: 'bg-destructive/10 text-destructive',
  open: 'bg-green-500/15 text-green-700 dark:text-green-400',
}

const LiveDemo = () => {
  const [enabled, setEnabled] = useState(false)
  const [events, setEvents] = useState<string[]>([])
  const { status } = useLive({
    enabled,
    onMessage: (msg) => setEvents((e) => [`${new Date().toLocaleTimeString()} ${msg.type}`, ...e].slice(0, 5)),
  })

  return (
    <Demo className="flex-col items-stretch">
      <div className="flex flex-wrap items-center gap-3">
        <code className="font-mono text-[11px]">{liveUrl()}</code>
        <Label className="gap-2"><Switch checked={enabled} onCheckedChange={setEnabled} />enabled</Label>
        <Badge className={statusColor[status]}>{status}</Badge>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Without a backend it cycles between connecting and reconnecting, which is expected. With the backend up it goes to open, and messages (<code>state</code>, <code>trip_started</code>…) show up here while a trip runs.
      </p>
      {events.map((e, i) => <code key={i} className="font-mono text-[11px]">{e}</code>)}
    </Demo>
  )
}

const HooksPage = () => {
  const [search, setSearch] = useState('')
  const debounced = useDebounce(search, 400)
  const isVisible = useVisibility()
  const logEntry = (visible: boolean) => `${new Date().toLocaleTimeString()} — ${visible ? 'visible' : 'hidden'}`
  const [visibilityLog, setVisibilityLog] = useState(() => [logEntry(isVisible)])
  const [lastVisible, setLastVisible] = useState(isVisible)

  // Log each change — "adjust state while rendering" instead of an effect
  if (lastVisible !== isVisible) {
    setLastVisible(isVisible)
    setVisibilityLog((log) => [logEntry(isVisible), ...log].slice(0, 5))
  }

  return (
    <DocPage
      title="Hooks"
      intro={<>From <code>@/hooks/*</code>. <code>useDebounce</code>, <code>useVisibility</code> and <code>useLocalStorage</code> are default exports. <code>useLive</code> is a named export.</>}
      toc={[['use-debounce', 'useDebounce'], ['use-visibility', 'useVisibility'], ['use-local-storage', 'useLocalStorage'], ['use-live', 'useLive']]}
    >
      <DocSection id="use-debounce" title="useDebounce" importLine="import useDebounce from '@/hooks/useDebounce'">
        <P>Returns <code>value</code> once it has stopped changing for <code>delay</code> ms. Use it for search-as-you-type, so you send one request instead of one per keystroke.</P>
        <Demo className="flex-col items-start">
          <Input className="max-w-xs" placeholder="Type fast…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <Readout label="live:">{search || '—'}</Readout>
          <Readout label="debounced (400ms):">{debounced || '—'}</Readout>
        </Demo>
        <Code>{`
          const [query, setQuery] = useState('')
          const debouncedQuery = useDebounce(query, 300)   // default 500ms

          useEffect(() => {
            if (debouncedQuery) api.get('/api/search', { params: { q: debouncedQuery } }).then(…)
          }, [debouncedQuery])
        `}</Code>
      </DocSection>

      <DocSection id="use-visibility" title="useVisibility" importLine="import useVisibility from '@/hooks/useVisibility'">
        <P><code>true</code> while the tab is visible, from <code>document.hidden</code>. Use it to pause polling, animations or the camera when the user switches tabs. Try switching tabs and coming back.</P>
        <Demo className="flex-col items-start">
          <Readout label="isVisible:">{String(isVisible)}</Readout>
          {visibilityLog.map((l, i) => <span key={i} className="font-mono text-[11px] text-muted-foreground">{l}</span>)}
        </Demo>
        <Code>{`
          const isVisible = useVisibility()
          useEffect(() => {
            if (!isVisible) return
            const id = setInterval(refetch, 5000)   // poll only while the tab is visible
            return () => clearInterval(id)
          }, [isVisible])
        `}</Code>
      </DocSection>

      <DocSection id="use-local-storage" title="useLocalStorage" importLine="import useLocalStorage from '@/hooks/useLocalStorage'">
        <P>
          A <code>useState</code> that persists to localStorage as JSON. Every component that uses the same key stays in sync, in this tab and in other tabs.
          It replaces the old "localStorage + <code>window.dispatchEvent('queue_state_changed')</code>" pattern. Click +1 in either card, or open this page in a second tab.
        </P>
        <Demo>
          <CounterCard name="Component A" />
          <CounterCard name="Component B" />
        </Demo>
        <Code>{`
          const [session, setSession, clearSession] = useLocalStorage<Session | null>('session', null)

          setSession({ ticketId: 42, queue: 'A' })
          setSession((prev) => prev && { ...prev, ticketId: 43 })   // functional update
          clearSession()                                             // removes the key → back to initial value
        `}</Code>
        <Props rows={[
          ['key', 'string', '', 'localStorage key'],
          ['initialValue', 'T', '', 'Used while the key is missing or unparsable. Captured once, so inline literals are fine'],
          ['returns', '[value, setValue, remove]', '', 'setValue accepts a value or (prev) => next'],
        ]} />
      </DocSection>

      <DocSection id="use-live" title="useLive" importLine="import { useLive, liveUrl } from '@/hooks/useLive'">
        <P>
          The backend's receive-only WebSocket (<code>/api/v1/ws</code>, docs/API.md §6). It never gives up: a dropped or failed connection retries after 1, 2, 4 and 8 s, then every 10 s.
          <code>onOpen</code> runs after every connect <em>and reconnect</em>; the server sends the current <code>state</code> right away if a trip is active. Handlers can be inline functions; only <code>url</code> or <code>enabled</code> reconnect.
        </P>
        <LiveDemo />
        <Code>{`
          const { status } = useLive({
            onOpen: () => setAwaitingState(true),
            onMessage: (msg: LiveMessage) => {
              if (msg.type === 'state') setTrip(msg.data)
              if (msg.type === 'trip_ended') setSummary(msg.data)
            },
          })
        `}</Code>
        <Props rows={[
          ['url', 'string', 'liveUrl()', "Dev: same-origin /api/v1/ws via the Vite proxy (ws: true). Build: VITE_API_URL's host"],
          ['onMessage', '(msg: LiveMessage) => void', '', 'Every server message, parsed (types in @/api/types)'],
          ['onOpen', '() => void', '', 'After every connect and reconnect'],
          ['enabled', 'boolean', 'true', 'false = no connection'],
          ['returns', '{ status }', '', "status: 'idle' | 'connecting' | 'open' | 'reconnecting'"],
        ]} />
      </DocSection>
    </DocPage>
  )
}

export default HooksPage
