# Hackathon starter

These are the reusable parts of the Hakaton2026 frontend (branch `frontend` @ `b0649b9`), cleaned up and made generic. The app-specific code for queues, branches and counters is gone.

**Stack:** Vite 8 · React 19 · TypeScript · Tailwind v4 · shadcn/ui (Radix + Hugeicons) · React Router 7 · axios · zod + react-hook-form · motion · sonner · next-themes

```bash
cp .env.example .env     # set VITE_API_URL
npm install
npm run dev
```

You can add more shadcn components when you need them, e.g. `npx shadcn@latest add dialog table tabs tooltip sheet`.

**Docs and live examples for everything:** run `npm run dev` and open **http://localhost:5173/usage-examples**. It's mounted by a single line in `src/App.tsx`. Delete that line to remove it from the product, and optionally delete `src/showcase/` too.

## What's inside

| Path | What it is |
|---|---|
| `components/ui/` | shadcn: badge, button, card, checkbox, dropdown-menu, input, input-group, label, select, separator, skeleton, sonner, switch, textarea |
| `components/layout/PhoneFrame` | iPhone frame for demoing a mobile app on a laptop or projector. Goes full-screen on real phones |
| `components/layout/MobileNav` | Bottom tab bar (`items`, `active`, `onChange`, optional badge dot) |
| `components/layout/SidebarLayout` | Admin dashboard shell: sidebar with NavLinks plus a scrollable `<Outlet />`. `SidebarButton` for logout and similar actions |
| `components/layout/RequireAuth` | Route guard, with optional `roles={['admin']}` |
| `components/shared/LoginForm` | Username and password card with zod validation |
| `components/shared/DataTable` | TanStack table with loading, error and empty states |
| `components/shared/QrScanner` | Camera QR scanner: picks the back camera, lets you switch cameras, can read from an image file. `onScan(text)` |
| `components/shared/Modal` | Blurred overlay in a portal. Locks scroll without shifting the layout. Wrap it in `<AnimatePresence>` to animate the exit |
| `components/shared/Onboarding` | Intro screens with back, skip, next and progress dots |
| `components/shared/SplashScreen` | App launch animation |
| `components/shared/Section`, `BackButton` | Small helpers |
| `context/AuthContext` | JWT in localStorage, decoded claims and roles, `login(token)` / `logout()`, auto-logout on 401 |
| `utils/api/client` | axios instance: base URL, Bearer token, 401 handling, ngrok header. `API_BASE_URL` |
| `utils/jwt` | `decodeJwt` (UTF-8 safe), `isJwtExpired`, `getJwtRoles` (understands ASP.NET's role claim URI) |
| `hooks/useLive` | Backend WebSocket (`/api/v1/ws`) that keeps retrying until the backend is back. `onOpen` runs after every reconnect |
| `hooks/useLocalStorage` | `useState` persisted to localStorage, synced across components and tabs |
| `hooks/useDebounce`, `useVisibility` | Debounced value, and whether the tab is visible |
| `pages/ErrorPage` | Router `errorElement`: 404 page with an animated link, plus a generic error page |
| `utils/css/` | SCSS media query variables and `mapped($min, $max)`, a fluid value clamped between the 402px and 1440px viewports |
| `utils/dom/documentManager` | Stackable scroll locks and an inert `#root` |
| `utils/math`, `utils/parsers/pathParser` | `round`/`adjust` (remap a range), and SVG path ↔ points for morphing animations |

Every component has its own folder (component, private child components, `.scss`, and an `index.ts`). The barrels chain upwards, so `import { DataTable, PhoneFrame } from '@/components'`, `import { ErrorPage, LoginPage } from '@/pages'` and `import { useAuth } from '@/context'` all work. `components/ui/` stays flat for the shadcn CLI.

`App.tsx` and `pages/LoginPage/` are a minimal example of how the pieces connect: a public page, a login page, and a protected `/admin` route using `SidebarLayout`.

## Snippets

```tsx
// Live backend WebSocket (/api/v1/ws), reconnects forever
const { status } = useLive({
  onMessage: (msg: LiveMessage) => { if (msg.type === 'state') setTrip(msg.data) },
})

// Table
const col = createColumnHelper<User>()
<DataTable data={users} isLoading={loading} columns={[
  col.accessor('name', { header: 'Name' }),
  col.accessor('email', { header: 'Email' }),
]} />

// Bottom nav
<MobileNav active={tab} onChange={setTab} items={[
  { key: 'home', label: 'Home', icon: Home01Icon },
  { key: 'tickets', label: 'Tickets', icon: Ticket01Icon, badge: hasTicket },
]} />
```

## Notes

- **Dev proxy:** in dev, `/api` and `/hubs` are proxied to `VITE_API_URL`, so you don't need CORS while developing. In production, requests go straight to `VITE_API_URL`, so the backend has to allow CORS.
- **ngrok:** both the axios client and the proxy send `ngrok-skip-browser-warning`, so an ngrok-tunnelled backend works without the interstitial page.
- **Camera:** browsers only allow camera access on HTTPS or `localhost`. To test on a phone, use an ngrok URL rather than `http://192.168.x.x`.
- **Login endpoint:** `LoginPage` posts to `/api/auth/login` and expects `{ token }` back. Change that to match your backend.
- **Barrel imports:** importing from `@/components/shared` is fine. `"sideEffects"` in `package.json` lets unused components (QrScanner pulls in about 370 KB) be dropped from the build.
- **Dark mode:** `ThemeProvider` in `main.tsx` toggles the `.dark` class. Switch themes with `useTheme()` from next-themes.
