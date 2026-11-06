// Injected by vite.config.ts `define` at dev/build time

/** Repo-root config/brand.json: the single source of truth for the app name */
declare const __BRAND__: { name: string; shortName?: string; tagline?: string }

/** This laptop's LAN IPv4 ('' if none was found), for the phone QR code */
declare const __LAN_IP__: string

/** The backend port the phone should use: VITE_API_URL's port when it runs on this laptop, else 8000 */
declare const __BACKEND_PORT__: number
