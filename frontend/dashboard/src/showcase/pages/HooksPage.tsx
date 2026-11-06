import { useState } from 'react'
import useDebounce from '@/hooks/useDebounce'
import useVisibility from '@/hooks/useVisibility'
import useLocalStorage from '@/hooks/useLocalStorage'
import { useSignalR, type HubConnectionState } from '@/hooks/useSignalR'
import { API_BASE_URL } from '@/utils/api/client'
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

const stateColor: Record<HubConnectionState, string> = {
  disconnected: 'bg-muted text-muted-foreground',
  connecting: 'bg-yellow-500/15 text-yellow-700 dark:text-yellow-400',
  reconnecting: 'bg-yellow-500/15 text-yellow-700 dark:text-yellow-400',
  connected: 'bg-green-500/15 text-green-700 dark:text-green-400',
  error: 'bg-destructive/10 text-destructive',
}

const SignalRDemo = () => {
  const [url, setUrl] = useState(`${API_BASE_URL}/hubs/queue`)
  const [enabled, setEnabled] = useState(false)
  const [events, setEvents] = useState<string[]>([])
  const { state } = useSignalR({
    url,
    enabled,
    handlers: { TicketCalled: (data: unknown) => setEvents((e) => [JSON.stringify(data), ...e].slice(0, 5)) },
  })

  return (
    <Demo className="flex-col items-stretch">
      <div className="flex flex-wrap items-center gap-3">
        <Input className="max-w-xs font-mono" value={url} onChange={(e) => setUrl(e.target.value)} />
        <Label className="gap-2"><Switch checked={enabled} onCheckedChange={setEnabled} />enabled</Label>
        <Badge className={stateColor[state]}>{state}</Badge>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Without a backend it cycles between connecting and error while it retries, which is expected. With a hub running at that URL it goes to connected, and <code>TicketCalled</code> events show up here.
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
      intro={<>From <code>@/hooks/*</code>. <code>useDebounce</code>, <code>useVisibility</code> and <code>useLocalStorage</code> are default exports. <code>useSignalR</code> is a named export.</>}
      toc={[['use-debounce', 'useDebounce'], ['use-visibility', 'useVisibility'], ['use-local-storage', 'useLocalStorage'], ['use-signalr', 'useSignalR']]}
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

      <DocSection id="use-signalr" title="useSignalR" importLine="import { useSignalR } from '@/hooks/useSignalR'">
        <P>
          Connects to an ASP.NET Core SignalR hub and never gives up. A dropped connection retries after 0, 2 and 5 s, then every 10 s, and so does a first connect that fails (e.g. the backend isn't up yet).
          <code>onConnected</code> runs after every connect <em>and reconnect</em>. Join groups and refetch state there, because the server forgets group membership when the connection drops and anything sent while you were offline is lost. Handlers can be inline functions; only changing the set of event names reconnects.
        </P>
        <SignalRDemo />
        <Code>{`
          const { state, connection } = useSignalR({
            url: \`\${API_BASE_URL}/hubs/queue\`,   // dev: '/hubs/queue' via the Vite proxy (ws: true)
            accessToken: token,                 // sent as ?access_token= (configure JwtBearerEvents.OnMessageReceived on the server)
            enabled: !!queueId,
            onConnected: (conn) => conn.invoke('JoinQueue', String(queueId)),
            handlers: {
              TicketCalled: (e: TicketCallEvent) => toast(\`Ticket \${e.ticketNumber} → counter \${e.counterId}\`),
            },
          })

          // client → server (invoke throws while reconnecting)
          if (state === 'connected') await connection?.invoke('SendMessage', 'hi')
        `}</Code>
        <Props rows={[
          ['url', 'string', '', 'Full hub URL'],
          ['accessToken', 'string | null', '', 'JWT for [Authorize] hubs'],
          ['handlers', 'Record<string, (...args) => void>', '{}', 'Server → client events'],
          ['onConnected', '(conn) => void | Promise', '', 'Runs after connect and every reconnect: join groups, refetch'],
          ['enabled', 'boolean', 'true', 'false = no connection'],
          ['returns', '{ connection, state }', '', "state: 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error' ('error' = failed, retrying)"],
        ]} />
      </DocSection>
    </DocPage>
  )
}

export default HooksPage
