declare module '*&imagetools' {
  import type { Picture } from 'vite-imagetools'
  const out: Picture
  export default out
}

declare module '*&imagetoolsraw' {
  const out: string
  export default out
}

// `?defaultopt` — see defaultDirectives in vite.config.ts
declare module '*?defaultopt' {
  import type { Picture } from 'vite-imagetools'
  const out: Picture
  export default out
}
