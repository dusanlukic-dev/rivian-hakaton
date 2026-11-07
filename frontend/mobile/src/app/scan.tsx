import { CameraView, useCameraPermissions } from 'expo-camera';
import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { openAppSettings } from '@/alerts/notifications';
import { normalizeAddress } from '@/api/address';
import { Button, Card, Icon, Screen, STACK_EDGES, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { settingsStore } from '@/state/settings';
import { colors, radius } from '@/theme/colors';

/**
 * Reads the QR code on the car screen (web dashboard, "Connect phone" card): payload "<lan-ip>:8000", any URL form
 * also works. Saves it as the car computer's address and goes back to the connection screen, which reconnects.
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
                const address = normalizeAddress(data);
                if (!address) return;
                setDone(true);
                settingsStore.set({ address });
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
