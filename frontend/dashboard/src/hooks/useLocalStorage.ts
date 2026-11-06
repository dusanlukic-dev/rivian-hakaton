import { useCallback, useMemo, useState, useSyncExternalStore } from 'react'

// `storage` only fires in *other* tabs, so same-tab writes announce themselves with this event
const SAME_TAB_EVENT = 'local-storage'

function subscribe(callback: () => void) {
    window.addEventListener('storage', callback)
    window.addEventListener(SAME_TAB_EVENT, callback)
    return () => {
        window.removeEventListener('storage', callback)
        window.removeEventListener(SAME_TAB_EVENT, callback)
    }
}

function parse<T>(raw: string | null, fallback: T): T {
    if (raw === null) return fallback
    try {
        return JSON.parse(raw) as T
    } catch {
        return fallback
    }
}

/**
 * `useState` backed by localStorage (JSON). Every component using the same key stays in sync,
 * across tabs too.
 */
function useLocalStorage<T>(key: string, initialValue: T) {
    // Captured once so an inline object/array literal doesn't change identity every render
    const [fallback] = useState(initialValue)
    const raw = useSyncExternalStore(subscribe, () => localStorage.getItem(key))
    const value = useMemo(() => parse(raw, fallback), [raw, fallback])

    const setValue = useCallback((next: T | ((prev: T) => T)) => {
        const prev = parse(localStorage.getItem(key), fallback)
        const resolved = next instanceof Function ? next(prev) : next
        localStorage.setItem(key, JSON.stringify(resolved))
        window.dispatchEvent(new Event(SAME_TAB_EVENT))
    }, [key, fallback])

    const remove = useCallback(() => {
        localStorage.removeItem(key)
        window.dispatchEvent(new Event(SAME_TAB_EVENT))
    }, [key])

    return [value, setValue, remove] as const
}

export default useLocalStorage
