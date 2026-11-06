// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    // android/ is generated (CNG); example/ is the local-only copy of the template demo
    ignores: ['dist/*', 'android/*', 'example/*'],
  },
]);
