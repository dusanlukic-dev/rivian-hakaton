/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // The car computer (FastAPI backend). Dev: /api and the camera WebSocket are proxied here, so there is no CORS
  const target = loadEnv(mode, process.cwd(), '').VITE_API_URL || 'http://localhost:8000'

  return {
    resolve: {
      tsconfigPaths: true,
    },
    plugins: [react(), tailwindcss()],
    // The sender worker is an ES module (new Worker(new URL(...), { type: 'module' }))
    worker: {
      format: 'es',
    },
    server: {
      port: 5174, // the dashboard runs on 5173
      proxy: {
        // ws: true so WS /api/v1/camera/ws goes through as well
        '/api': { target, ws: true, changeOrigin: true },
      },
    },
    test: {
      environment: 'node',
      include: ['src/**/*.test.ts'],
    },
  }
})
