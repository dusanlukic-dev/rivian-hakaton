import { CameraView, useCameraPermissions } from 'expo-camera';
import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { normalizeAddress } from '@/api/address';
import { Button, Card, Screen, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { settingsStore } from '@/state/settings';
import { colors, radius } from '@/theme/colors';

/** Scans the QR on the web dashboard ("Connect phone" card): payload "<lan-ip>:8000" (any URL form also works). */
export default function ScanScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [done, setDone] = useState(false);

  if (!permission) return <View style={styles.black} />;

  if (!permission.granted) {
    return (
      <Screen>
        <Card>
          <Txt>{strings.scan.permission}</Txt>
          <Button label={strings.scan.grant} icon="camera" onPress={() => void requestPermission()} />
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
      <View style={styles.hint}>
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
    bottom: 48,
    left: 24,
    right: 24,
    padding: 14,
    borderRadius: radius.md,
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  center: { textAlign: 'center' },
});
