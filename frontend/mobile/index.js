// Custom entry (package.json "main"). Registers notify-kit's headless handlers before Expo Router boots the app.
import notifee, { EventType } from 'react-native-notify-kit';
import 'expo-router/entry';

import { ackEmergency } from './src/state/live';

// Drive-mode foreground service: the runner never resolves, so the service (and the WebSocket in JS)
// stays alive until notifee.stopForegroundService() is called when the trip ends.
notifee.registerForegroundService(() => new Promise(() => {}));

// "I'm OK" pressed on the emergency notification while the app is in the background.
notifee.onBackgroundEvent(async ({ type, detail }) => {
  if (type === EventType.ACTION_PRESS && detail.pressAction?.id === 'ack') ackEmergency();
});
