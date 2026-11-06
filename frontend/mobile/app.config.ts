import type { ConfigContext, ExpoConfig } from 'expo/config';

// Single source of truth for the app name: repo-root config/brand.json (also read by the web dashboard).
// Changing `name` needs `npm run prebuild` + `npm run android` (it's the Android launcher label).
import brand from '../../config/brand.json';

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: brand.name,
  slug: config.slug ?? 'safety-reviewer',
  extra: { ...config.extra, brand },
});
