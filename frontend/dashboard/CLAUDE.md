# Dashboard (web "car screen"): stack notes for Claude

This app started as the user's reusable hackathon starter (copied from `fh26/extracted` on 2026-11-06). Everything below is the starter's original guide and still applies. **Project-specific rules** (purpose, WebSocket instead of SignalR, sound unlock, sim panel) are in `../../.claude/rules/dashboard.md`. Run every command below from `frontend/dashboard/`.

A reusable Vite + React 19 + TS + Tailwind v4 + shadcn starter. It was extracted from the Hakaton2026 frontend (branch `frontend` @ `b0649b9`), with the domain code (queues, branches, counters) removed. The user reuses it at hackathons, so speed and simplicity win over abstraction.

## Commands

```bash
npm run dev      # Vite; /api (incl. WebSocket) and /hubs proxied to VITE_API_URL (.env, default http://localhost:8000)
npm run build    # tsc -b && vite build — run this to verify changes
npm run lint     # eslint; 1 expected warning (DataTable: react-hooks/incompatible-library)
```

Visual check without asking the user: run `npm run build`, then `npx vite preview --port 4173` in the background, then
`"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --user-data-dir=<scratch> --window-size=1400,900 --virtual-time-budget=6000 --screenshot=<file>.png <url>`
and Read the PNG. `--dump-dom` gives the rendered HTML instead.

## Rules (follow these)

- Imports: always `@/…` (→ `src/`). This is the only alias.
- Icons: **Hugeicons only**. `import { HugeiconsIcon, type IconSvgElement } from '@hugeicons/react'` and icons from `@hugeicons/core-free-icons`. No heroicons or bootstrap-icons. Check that a name exists in `node_modules/@hugeicons/core-free-icons/dist/types/index.d.ts` before using it.
- Animation: `motion/react`, not `framer-motion`, which isn't installed.
- Classes: merge with `cn()` from `@/lib/utils`. Use theme tokens (`bg-background`, `text-muted-foreground`, `bg-primary`…), never hardcoded white or black, so dark mode keeps working.
- New shadcn components: `npx shadcn@latest add <name>` → `src/components/ui/`. The eslint `react-refresh/only-export-components` rule is turned off for `components/ui/**` only.
- **One component per folder**, even single-file ones: `Name/{Name.tsx, Name.scss?, PrivateChild.tsx…, index.ts}`. Child components only that component uses live in its folder and are *not* exported from its `index.ts`. `index.ts` re-exports the default as named: `export { default as Name, type NameThing } from './Name'`. Then add `export * from './Name'` to the parent barrel (`shared/index.ts`, `layout/index.ts`, `pages/index.ts`). `components/index.ts` re-exports `layout` + `shared`. `components/ui/` is the exception and stays flat (the shadcn CLI writes `ui/<name>.tsx` and its components import each other by that path).
- A `.tsx` must export only components (react-refresh rule). Put hooks, helpers and contexts in sibling `.ts` files in the same folder (e.g. `context/AuthContext/{AuthContext.ts, AuthProvider.tsx, useAuth.ts}`, `SidebarLayout/sidebarItemClass.ts`). Exporting types from a `.tsx` is fine.
- eslint-plugin-react-hooks v7 includes React Compiler rules: no sync `setState` in an effect body (`set-state-in-effect`), and no reading or writing `ref.current` during render (`refs`). To adjust state when a value changes, use the "compare to previous value during render" pattern. Update callback refs inside a `useEffect` without deps.
- Sass `@use` can't resolve `@/`, so use relative paths (`@use '../utils/css/functions'`).
- UI strings: the defaults are Serbian where the original was Serbian (LoginForm, Onboarding, DataTable, BackButton) and English elsewhere. Every string is a prop.
- **When you add or change a shared component, hook or util, update its showcase page** (`src/showcase/pages/*`). The showcase is the documentation.

## Map of src/

| Path | Notes |
|---|---|
| `main.tsx` | `ThemeProvider` (next-themes, `.dark` class) + `<Toaster />` + `<App />` |
| `App.tsx` | `AuthProvider` → `createBrowserRouter(createRoutesFromElements(...))`. Pathless root route has `errorElement={<ErrorPage />}`. Example: `/`, `/login`, `RequireAuth` → `/admin` (SidebarLayout). Last line: showcase |
| `components/ui/` | shadcn (style radix-mira). Button sizes are small (`h-7` default); `size="lg" className="py-6"` for mobile CTAs. Badge default = `bg-primary` |
| `components/index.ts` | `export * from './layout'` + `'./shared'`, so everything below imports from `@/components` too |
| `components/layout/` (barrel) | `PhoneFrame/`, `MobileNav/`, `RequireAuth/`, `SidebarLayout/` (also exports `SidebarButton`; private `SidebarLink` + `sidebarItemClass.ts`) |
| `components/shared/` (barrel) | `LoginForm/`, `DataTable/`, `QrScanner/` (private `QrBoxOutline`), `Modal/`, `Onboarding/`, `SplashScreen/`, `Section/`, `BackButton/` |
| `context/AuthContext/` (barrel, also `@/context`) | `AuthProvider`, `useAuth()`, `type AuthContextValue`; files `AuthContext.ts` (createContext), `AuthProvider.tsx`, `useAuth.ts` |
| `hooks/` | `useDebounce` (default), `useVisibility` (default), `useLocalStorage` (default), `useLive` (named: backend WebSocket `/api/v1/ws`, never-give-up reconnect, `liveUrl()`) |
| `api/` | `types.ts` = docs/API.md §4 verbatim (identical to mobile). `trips.ts`: `startTrip`, `endTrip`, `postTelemetry`, `localIsoTimestamp`, `httpStatus`, `errorMessage` |
| `pages/CarScreen/` | `/` = the car screen. `useCarScreen.ts` (live state + sound reactions), `audio.ts` (clips + remembered sound choice), `carMeta.ts` (labels, lamp colours as words and CSS variables), private children (StatusPanel, BehaviorTiles, SimulatorPanel, Chip, Wordmark…). Styled with the Vigil design system, see `../../.claude/rules/dashboard.md`. `?sim` opens the simulator |
| `utils/api/client.ts` | default axios `api`; `API_BASE_URL`, `TOKEN_KEY='auth_token'`, `UNAUTHORIZED_EVENT='auth:unauthorized'` |
| `utils/jwt.ts` | `decodeJwt`, `isJwtExpired`, `getJwtRoles` |
| `utils/css/` | `_functions.scss` → `mapped($min, $max, $min-vw: 402px, $max-vw: 1440px)` (clamped fluid value); `_mediaqueries.scss` → `$phone`, `$tablet`, `$desktop`… |
| `utils/dom/documentManager.ts` | `lockScroll(value) → { release }` (stackable, first lock wins), `enableInertRoot()/disableInertRoot()` |
| `utils/math/math.ts`, `utils/parsers/pathParser.ts` | `round`, `adjust` (range remap); `parsePath`/`encodePath` (absolute M L H V C Z only) |
| `pages/` (barrel: `import { ErrorPage, LoginPage } from '@/pages'`) | |
| `pages/ErrorPage/` | 404 (private `PageNotFound`) via `isRouteErrorResponse(...).status === 404`, else `DefaultError`. Logs the error in DEV. Styles in `ErrorPage.scss` |
| `pages/LoginPage/` | Example: posts `/api/auth/login`, expects `{ token }`, calls `login()`, redirects to `state.from` |
| `types/declarations/` | `env.d.ts` (`VITE_API_URL`), `imagetools.d.ts` (`?defaultopt` → `Picture`), `globals.d.ts` (`__BRAND__` from repo-root `config/brand.json`, `__LAN_IP__`, `__BACKEND_PORT__`: injected by `vite.config.ts` `define`) |
| `showcase/` | Living docs. See below |

## API cheat sheet

```ts
<PhoneFrame>{children}</PhoneFrame>                       // fixed inset-0; frame on ≥sm, full-screen on phones; scroll el id="phone-container"
<MobileNav<K> items={{ key, label, icon, badge? }[]} active={k} onChange={setK} className? />   // sticky bottom-0 mt-auto → last child of flex-col
<SidebarLayout brand items={{ label, to, icon, end? }[]} bottomItems? footer? children? />      // layout route → renders <Outlet/>
<SidebarButton label icon onClick />
<RequireAuth roles?={string[]} redirectTo?='/login' forbiddenTo?='/' />                    // layout route; sets state.from
<LoginForm onSubmit={async (v: LoginValues) => {...}} brand? title? description? errorMessage? />  // throw → shows errorMessage; fixed inset-0
<DataTable data columns={ColumnDef<T, any>[]} isLoading? error? emptyMessage? loadingMessage? onRowClick? />
<QrScanner onScan={(text) => …} stopOnScan?=true className? />  // h-full: parent needs a height; HTTPS/localhost only; useId per instance
<AnimatePresence>{open && <Modal animateInitial className="flex items-center justify-center bg-black/30" onBackgroundClick={close}>…</Modal>}</AnimatePresence>
<Onboarding steps={{ title, subtitle?, image? }[]} onFinish labels?={{ back, skip, next, finish }} />
<SplashScreen>{logo}</SplashScreen>
<Section heading? isContainer?=true {...sectionProps} />   <BackButton to? label?='Nazad' />

const { token, claims, roles, isAuthenticated, login, logout } = useAuth()
const debounced = useDebounce(value, 500)
const isVisible = useVisibility()
const [value, setValue, remove] = useLocalStorage<T>(key, initial)    // setValue(v | prev => v); syncs across components + tabs
const { status } = useLive({ onMessage: (msg: LiveMessage) => …, onOpen?, url?=liveUrl(), enabled? })   // 'idle' | 'connecting' | 'open' | 'reconnecting'
```

## Non-obvious behaviour and gotchas

- **`"sideEffects": ["**/*.css", "**/*.scss"]` in package.json is load-bearing.** Without it, the barrel `@/components/shared` drags QrScanner (html5-qrcode, ~370 KB) into every build, because of its `.scss` import. Don't remove it. Any non-CSS module with real import-time side effects must be added to that list.
- **After moving or renaming files, the user's running `npm run dev` must be restarted.** Vite keeps serving cached transforms of unchanged importers, which still point at the old path. The browser then fails with `Loading module from ".../Old.tsx?t=..." was blocked because of a disallowed MIME type ("")`. Tell the user to restart and hard-refresh. Don't kill their dev server yourself; verify on another port (`npx vite --port 5179 --strictPort`).
- **next-themes + React 19:** `scriptProps={{ type: 'application/json' }}` on `ThemeProvider` (main.tsx) silences React's "Encountered a script tag" warning. The script is SSR-only and never runs in an SPA anyway.
- **Don't add `<Route path="*">` for 404s.** Unmatched URLs already reach the root `errorElement` as a 404 route error. A normal `*` route would render ErrorPage with no route error, so it would show the generic page instead.
- **Lazy routes need `hydrateFallbackElement={<></>}`** (or a `HydrateFallback` somewhere in the match). Otherwise React Router warns "No HydrateFallback element provided" when the first page load hits the lazy route.
- **Auth expiry:** `isJwtExpired` is only checked when the app loads (`readStoredToken`). During a session, expiry relies on the backend returning 401. The axios interceptor then clears the token and dispatches `UNAUTHORIZED_EVENT`, and AuthProvider logs out. The frontend never verifies signatures, so fake unsigned JWTs work (see `showcase/_kit/fakeJwt.ts`).
- **Dev vs prod URLs:** `API_BASE_URL` is `''` in dev (Vite proxy, no CORS) and `VITE_API_URL` in prod (the backend must allow CORS). `liveUrl()` derives the WebSocket URL from it. The proxy has `ws: true` for `/api` and `/hubs`.
- **ngrok:** both the axios client and the proxy send `ngrok-skip-browser-warning: true`.
- **useLive:** plain WebSocket, receive-only. It never gives up: retries after 1, 2, 4, 8 s, then every 10 s (the docs/API.md §6 pattern). The first connect is deferred one tick, so StrictMode's double mount doesn't open a throwaway socket. Handlers are read through a ref; only `url` or `enabled` reconnect. `onOpen` runs after every (re)connect, and the server sends the current `state` right away if a trip is active (CarScreen treats silence after a reconnect as "no trip").
- **Modal:** locks scroll through documentManager and pads `#root` by the measured scrollbar width (`.modal-open #root`). Only the first open modal measures. There's no Escape key handling or focus trap; for that, suggest `npx shadcn add dialog`.
- **PhoneFrame, LoginForm and ErrorPage** are `position: fixed` full-screen, so they can't be previewed inline (the showcase gives them their own routes).
- **SidebarLayout** has no mobile drawer. It's `h-dvh`, sidebar `w-56`, shell `max-w-360`.
- **Tailwind scans all of `src/`**, including `src/showcase/`, so the showcase's classes end up in the main CSS (~5 KB). Deleting the folder drops them.
- **pathParser:** throws on lowercase (relative) commands. `encodePath` always appends `Z`. Point shape: `{ x, y, xs?, ys?, xe?, ye? }` (start/end control handles).

## Showcase (`/usage-examples`)

- Mounted by **one line** in `App.tsx`: `<Route path='/usage-examples/*' lazy={() => import('@/showcase')} hydrateFallbackElement={<></>} />`. Deleting that line removes it entirely (verified: the main bundle went back to the same size). `src/showcase/` can then be deleted; nothing else imports it.
- It's lazy, so it's a separate chunk (~760 KB, which includes the QrScanner and TanStack code) that only downloads when visited.
- `showcase/index.tsx` exports `Component` (what React Router's `lazy` expects) and renders descendant `<Routes>`. Links are absolute, built from `BASE` in `showcase/base.ts`; keep it in sync with the App.tsx path.
- Pages: `pages/{Overview,UiPage,LayoutPage,ComponentsPage,HooksPage,AuthApiPage,UtilsPage,ErrorsPage}.tsx`. Full-screen demos: `demos/{PhoneDemo,LoginDemo,CrashDemo}.tsx` (registered outside the sidebar shell).
- Doc kit, `showcase/_kit/Doc.tsx`: `DocPage { title, intro?, toc?: [id, label][] }` (scrolls to `#hash` once mounted), `DocSection { id, title, importLine? }`, `P`, `Demo { label?, className? }`, `Code` (template string, auto-dedented, copy button), `Props { rows: [name, type, default, description][] }`, `Readout { label }`.
- To document a new thing: add a `DocSection` to the matching page (live `Demo` + `Code` + `Props`), and add it to that page's `toc`. A new page also needs a `<Route>` in `showcase/index.tsx`, an entry in its `items`, and a card in `Overview.tsx`'s `pages`.

## Deliberately not included

- The domain pages and API (filijale/salteri/tickets) and the brand assets (Pacifico font, images, `_colors.scss`).
- `CustomDropdown`: redundant with shadcn `select` and `dropdown-menu`.
- `getScrollBarWidth`: replaced by `innerWidth - clientWidth` in Modal.
- `lodash.debounce`.
- The .NET backend. The infrastructure worth reusing (Dockerfile, compose with mssql + redis, JWT setup, RedisService) lives on `origin/backend` of the Hakaton2026 repo, which is newer than the copy on `frontend`.
