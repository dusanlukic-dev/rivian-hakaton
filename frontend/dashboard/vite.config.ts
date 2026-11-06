import { defineConfig, loadEnv } from 'vite'
import { imagetools } from 'vite-imagetools'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_URL

  // ngrok shows an interstitial page to browsers unless this header is sent
  const headers = { 'ngrok-skip-browser-warning': 'true' }

  return {
    resolve: {
      tsconfigPaths: true,
    },
    plugins: [
      react(),
      tailwindcss(),
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
