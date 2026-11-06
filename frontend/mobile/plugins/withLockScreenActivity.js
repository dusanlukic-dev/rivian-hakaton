// Config plugin: lets MainActivity appear over the lock screen and switch the display on.
// Needed so a full-screen-intent alert (react-native-notify-kit `fullScreenAction`) can wake
// a sleeping/locked phone and show the red alert UI without the driver unlocking first.
// Side effect (accepted for the demo): while the app is the top activity it stays visible
// over the keyguard, like a navigation app.
const { withAndroidManifest, AndroidConfig } = require('expo/config-plugins');

module.exports = function withLockScreenActivity(config) {
  return withAndroidManifest(config, (cfg) => {
    const activity = AndroidConfig.Manifest.getMainActivityOrThrow(cfg.modResults);
    activity.$['android:showWhenLocked'] = 'true';
    activity.$['android:turnScreenOn'] = 'true';
    return cfg;
  });
};
