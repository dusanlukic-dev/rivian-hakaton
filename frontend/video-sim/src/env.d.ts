interface ImportMetaEnv {
  /** Backend base URL (.env). Dev proxies /api there; a build calls it directly */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
