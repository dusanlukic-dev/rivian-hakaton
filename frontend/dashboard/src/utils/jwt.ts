export type JwtClaims = Record<string, unknown>

/** Decodes the payload of a JWT. Client-side only — does NOT verify the signature. */
export function decodeJwt(token: string): JwtClaims {
    try {
        const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
        // atob gives a binary string; go through bytes so non-ASCII claims (č, ć, š...) decode correctly
        const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
        return JSON.parse(new TextDecoder().decode(bytes)) as JwtClaims
    } catch {
        return {}
    }
}

export function isJwtExpired(token: string): boolean {
    const exp = Number(decodeJwt(token).exp ?? 0)
    return exp > 0 && exp * 1000 < Date.now()
}

// ASP.NET Core writes roles under this URI unless the claim type is mapped to plain 'role'
const ASPNET_ROLE_CLAIM = 'http://schemas.microsoft.com/ws/2008/06/identity/claims/role'

/** Roles from the `role` claim (or the ASP.NET URI variant). A single role and an array of roles both work. */
export function getJwtRoles(claims: JwtClaims): string[] {
    const raw = claims.role ?? claims[ASPNET_ROLE_CLAIM]
    if (Array.isArray(raw)) return raw.filter((r): r is string => typeof r === 'string')
    return typeof raw === 'string' ? [raw] : []
}
