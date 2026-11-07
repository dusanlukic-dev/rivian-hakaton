// Expo's default Metro config, plus one thing: never crawl or watch native build output.
// After every native build (`npm run android`) Gradle writes thousands of files under node_modules/*/android/build and
// android/app/build; Metro's watcher choked on them and stopped answering for minutes (skill mobile-dev, Common errors).
// None of it is JavaScript, so ignoring it is safe. https://docs.expo.dev/guides/customizing-metro
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

const nativeBuildOutput = /[\\/]android[\\/](?:app[\\/])?(?:build|\.cxx|\.gradle)[\\/].*/;
const existing = config.resolver.blockList;
config.resolver.blockList = [...(Array.isArray(existing) ? existing : existing ? [existing] : []), nativeBuildOutput];

module.exports = config;
