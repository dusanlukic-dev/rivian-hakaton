import Constants from 'expo-constants';

/**
 * App name & tagline. Single source of truth: repo-root `config/brand.json`
 * (read by app.config.ts, which also sets the Android app name, and exposed here via `extra.brand`).
 */
export interface Brand {
  name: string;
  shortName: string;
  tagline: string;
}

const fromConfig = Constants.expoConfig?.extra?.brand as Partial<Brand> | undefined;

export const brand: Brand = {
  name: 'Safety Reviewer',
  shortName: 'Safety',
  tagline: '',
  ...fromConfig,
};
