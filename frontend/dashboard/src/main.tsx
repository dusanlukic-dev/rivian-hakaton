import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from 'next-themes'
import { Toaster } from '@/components/ui/sonner'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* Toggles the `.dark` class on <html>; `useTheme()` from next-themes to switch.
        next-themes' anti-flash <script> is for SSR and never runs in an SPA; a non-JS type stops React 19's "Encountered a script tag" warning */}
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem scriptProps={{ type: 'application/json' }}>
      <App />
      <Toaster />
    </ThemeProvider>
  </StrictMode>,
)
