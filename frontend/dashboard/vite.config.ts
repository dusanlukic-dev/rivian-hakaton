import { readFileSync } from 'node:fs'
import { createSocket } from 'node:dgram'
import { networkInterfaces } from 'node:os'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv, type Plugin } from 'vite'
import { imagetools } from 'vite-imagetools'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

interface Brand {
  name: string
  shortName?: string
  tagline?: string
}

/** Repo-root config/brand.json is the single source of truth for the app name */
function readBrand(): Brand {
  try {
    return JSON.parse(readFileSync(fileURLToPath(new URL('../../config/brand.json', import.meta.url)), 'utf8')) as Brand
  } catch {
    return { name: 'Car screen' }
  }
}

const firstLanIPv4 = () =>
  Object.values(networkInterfaces())
    .flat()
    .find((i) => i && i.family === 'IPv4' && !i.internal)?.address ?? ''

/**
 * This laptop's LAN IPv4, for the phone QR code. Same trick as backend/run.py: a UDP "connect" to 8.8.8.8 sends no packets,
 * it only makes the OS pick the interface with the default route. Fallback: the first non-internal IPv4.
 */
function lanIp(): Promise<string> {
  return new Promise((resolve) => {
    const socket = createSocket('udp4')
    let settled = false
    const done = (ip: string) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      try {
        socket.close()
      } catch {
        // already closed
      }
      resolve(ip && ip !== '0.0.0.0' ? ip : firstLanIPv4())
    }
    const timer = setTimeout(() => done(''), 1000)
    socket.on('error', () => done(''))
    socket.connect(80, '8.8.8.8', () => done(socket.address().address))
  })
}

/** Port the phone should use: VITE_API_URL's when the backend runs on this laptop, else the backend default 8000 */
function backendPort(apiUrl: string | undefined): number {
  try {
    const url = new URL(apiUrl ?? '')
    if (['localhost', '127.0.0.1', '0.0.0.0'].includes(url.hostname) && url.port) return Number(url.port)
  } catch {
    // not a URL
  }
  return 8000
}

const escapeHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

const brandTitle = (brand: Brand): Plugin => ({
  name: 'brand-title',
  transformIndexHtml: (html) => html.replace(/<title>.*?<\/title>/, `<title>${escapeHtml(brand.name)}</title>`),
})

// https://vite.dev/config/
export default defineConfig(async ({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_URL
  const brand = readBrand()

  // ngrok shows an interstitial page to browsers unless this header is sent
  const headers = { 'ngrok-skip-browser-warning': 'true' }

  return {
    resolve: {
      tsconfigPaths: true,
    },
    // Declared in src/types/declarations/globals.d.ts
    define: {
      __BRAND__: JSON.stringify(brand),
      // LAN_IP set (even empty) wins: the Docker build sets it empty, the container's own IP would be wrong for the phone
      __LAN_IP__: JSON.stringify(env.LAN_IP ?? (await lanIp())),
      __BACKEND_PORT__: JSON.stringify(backendPort(target)),
    },
    plugins: [
      react(),
      tailwindcss(),
      brandTitle(brand),
      imagetools({
        // `import hero from './hero.jpg?defaultopt'` → responsive <picture> sources (avif + webp, 300w/600w)
        defaultDirectives: (url) => {
          if (url.searchParams.has('defaultopt')) {
            return new URLSearchParams('w=300;600&format=avif;webp&as=picture')
          }
          return new URLSearchParams()
        },
      }),
    ],
    // In dev the API is proxied, so the browser only talks to the Vite origin and CORS never comes up
    server: target
      ? {
          proxy: {
            // ws: true so the FastAPI WebSocket at /api/v1/ws is proxied too
            '/api': { target, ws: true, changeOrigin: true, secure: false, headers },
            '/hubs': { target, ws: true, changeOrigin: true, secure: false, headers },
          },
        }
      : undefined,
  }
})
