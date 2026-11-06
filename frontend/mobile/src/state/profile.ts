import { persist } from '@/lib/persist';
import { createStore, useStore } from '@/lib/store';

/** Local "account": there is no auth on the backend, trips are keyed by driver_id. */
export interface Profile {
  name: string;
  driverId: string;
  contactName: string;
  contactPhone: string;
}

type ProfileState = Profile & { ready: boolean };

export const profileStore = createStore<ProfileState>({
  name: '',
  driverId: '',
  contactName: '',
  contactPhone: '',
  ready: false,
});

export async function loadProfile() {
  await persist(profileStore, 'profile.v1', ['name', 'driverId', 'contactName', 'contactPhone']);
  profileStore.set({ ready: true });
}

export function useProfile<S>(select: (state: ProfileState) => S): S {
  return useStore(profileStore, select);
}

/** "Matija Radović" → "matija-radovic" */
export function slugify(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/đ/g, 'dj')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
