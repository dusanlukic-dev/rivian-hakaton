import AsyncStorage from '@react-native-async-storage/async-storage';

import type { Store } from './store';

function pick<T extends object>(source: Partial<T>, keys: (keyof T)[]): Partial<T> {
  const out: Partial<T> = {};
  for (const key of keys) if (source[key] !== undefined) out[key] = source[key];
  return out;
}

/** Loads `keys` of a store from AsyncStorage once, then writes them back whenever they change. */
export async function persist<T extends object>(store: Store<T>, storageKey: string, keys: (keyof T)[]): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(storageKey);
    if (raw) store.set(pick(JSON.parse(raw) as Partial<T>, keys));
  } catch {
    // corrupted or unavailable storage: keep defaults
  }
  let last = JSON.stringify(pick(store.get(), keys));
  store.subscribe(() => {
    const next = JSON.stringify(pick(store.get(), keys));
    if (next === last) return;
    last = next;
    AsyncStorage.setItem(storageKey, next).catch(() => {});
  });
}
