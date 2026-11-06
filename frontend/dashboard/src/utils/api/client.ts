import axios from 'axios'

export const TOKEN_KEY = 'auth_token'
/** Fired on window when an authenticated request gets a 401 — AuthProvider listens and logs out */
export const UNAUTHORIZED_EVENT = 'auth:unauthorized'

/** '' in dev (requests go through the Vite proxy), VITE_API_URL in prod. Use it for SignalR hub URLs too. */
export const API_BASE_URL = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL ?? '')

const api = axios.create({
    baseURL: API_BASE_URL,
    // ngrok shows an interstitial page to browsers unless this header is sent
    headers: { 'ngrok-skip-browser-warning': 'true' },
})

api.interceptors.request.use((config) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
        config.headers.Authorization = `Bearer ${token}`
    }
    return config
})

api.interceptors.response.use(
    (response) => response,
    (error: unknown) => {
        if (axios.isAxiosError(error) && error.response?.status === 401 && localStorage.getItem(TOKEN_KEY)) {
            localStorage.removeItem(TOKEN_KEY)
            window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
        }
        return Promise.reject(error)
    }
)

export default api
