const base64url = (json: unknown) => {
  const bytes = new TextEncoder().encode(JSON.stringify(json))
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Unsigned JWT for demos — the frontend never verifies signatures, so this is enough to drive AuthContext */
export function makeFakeJwt(claims: Record<string, unknown>, expiresInSeconds = 3600) {
  const payload = { exp: Math.floor(Date.now() / 1000) + expiresInSeconds, ...claims }
  return `${base64url({ alg: 'none', typ: 'JWT' })}.${base64url(payload)}.fake-signature`
}
