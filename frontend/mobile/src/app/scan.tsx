import { CameraView, useCameraPermissions } from 'expo-camera';
import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { openAppSettings } from '@/alerts/notifications';
import { parseConnectLink } from '@/api/address';
import { Button, Card, Icon, Screen, STACK_EDGES, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { settingsStore } from '@/state/settings';
import { colors, radius } from '@/theme/colors';

/**
 * Reads the QR code on the car screen (web dashboard, "Connect phone" card):
 * `driveralert://connect?server=<host:port>&car=<host:port>` sets the server's and the car computer's addresses.
 * A bare address (the older QR code, any URL form) is the car computer's. Then goes back to the screen that opened it.
 */
export default function ScanScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [done, setDone] = useState(false);
  const insets = useSafeAreaInsets();

  if (!permission) return <View style={styles.black} />;

  if (!permission.granted) {
    const blocked = !permission.canAskAgain;
    return (
      <Screen edges={STACK_EDGES}>
        <Card>
          <Icon name="camera-outline" size={28} color={colors.muted} />
          <Txt>{blocked ? strings.scan.blocked : strings.scan.permission}</Txt>
          {blocked ? (
            <Button label={strings.scan.openSettings} icon="open-in-new" onPress={() => void openAppSettings()} />
          ) : (
            <Button label={strings.scan.grant} icon="camera" onPress={() => void requestPermission()} />
          )}
        </Card>
      </Screen>
    );
  }

  return (
    <View style={styles.black}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={
          done
            ? undefined
            : ({ data }) => {
                const link = parseConnectLink(data);
                if (!link) return;
                setDone(true);
                settingsStore.set(link);
                router.back();
              }
        }
      />
      <View style={styles.frame} />
      <View style={[styles.hint, { bottom: insets.bottom + 24 }]}>
        <Txt weight="600" style={styles.center}>
          {strings.scan.hint}
        </Txt>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  black: { flex: 1, backgroundColor: '#000', alignItems: 'center', justifyContent: 'center' },
  frame: { width: 240, height: 240, borderRadius: radius.xl, borderWidth: 3, borderColor: colors.foreground },
  hint: {
    position: 'absolute',
    left: 24,
    right: 24,
    padding: 14,
    borderRadius: radius.md,
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  center: { textAlign: 'center' },
});
