import { router, useLocalSearchParams } from 'expo-router';
import { useEffect } from 'react';

import { connectFromParams } from '@/api/address';
import { settingsStore } from '@/state/settings';

/**
 * Deep link from the car screen's QR code, when it's scanned with the phone's own camera app:
 * `driveralert://connect?server=<host:port>&car=<host:port>`. Saves the addresses (same as the in-app scanner),
 * then opens the app as usual: the root guards show the login screen or the Drive tab.
 */
export default function ConnectLinkScreen() {
  const { server, car } = useLocalSearchParams<{ server?: string; car?: string }>();

  useEffect(() => {
    const link = connectFromParams(server, car);
    if (link) settingsStore.set(link);
    router.replace('/');
  }, [server, car]);

  return null;
}
