import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { normalizeAddress } from '@/api/address';
import { api } from '@/api/client';
import { Button, Card, Icon, SectionLabel, TextField, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { errorText } from '@/lib/format';
import { DEFAULT_ADDRESS, settingsStore } from '@/state/settings';
import { colors } from '@/theme/colors';

/**
 * The car computer's address (backend "host:port"): edit, test, USB preset, QR scan. Used by Settings and by the login
 * screen (a fresh phone has to reach the backend before it can log in). Key it by the saved address so a QR scan or
 * the USB preset refreshes the draft.
 */
export function ConnectionCard({ saved, label = true }: { saved: string; label?: boolean }) {
  const [draft, setDraft] = useState(saved);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [testing, setTesting] = useState(false);

  function save(value = draft) {
    const address = normalizeAddress(value);
    if (!address) {
      setResult({ ok: false, text: strings.settings.invalid });
      return null;
    }
    settingsStore.set({ address });
    return address;
  }

  async function test() {
    const address = normalizeAddress(draft);
    if (!address) {
      setResult({ ok: false, text: strings.settings.invalid });
      return;
    }
    setTesting(true);
    const started = Date.now();
    try {
      await api.health(address);
      setResult({ ok: true, text: strings.settings.testOk(Date.now() - started) });
    } catch (e) {
      setResult({ ok: false, text: errorText(e) });
    } finally {
      setTesting(false);
    }
  }

  return (
    <>
      {label ? <SectionLabel>{strings.settings.connection}</SectionLabel> : null}
      <Card>
        <TextField
          label={strings.settings.address}
          hint={strings.settings.addressHint}
          value={draft}
          onChangeText={(text) => {
            setDraft(text);
            setResult(null);
          }}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="10.190.62.27:8000"
          onSubmitEditing={() => save()}
        />
        {result ? (
          <View style={styles.row}>
            <Icon name={result.ok ? 'check-circle' : 'alert-circle-outline'} size={18} color={result.ok ? colors.ok : colors.destructive} />
            <Txt size="sm" style={[styles.flex, { color: result.ok ? colors.ok : colors.destructive }]}>
              {result.text}
            </Txt>
          </View>
        ) : null}
        <View style={styles.row}>
          <Button label={strings.settings.save} icon="content-save" disabled={draft.trim() === saved} onPress={() => save()} style={styles.flex} />
          <Button label={strings.settings.test} icon="lan-connect" variant="secondary" loading={testing} onPress={() => void test()} style={styles.flex} />
        </View>
        <View style={styles.row}>
          <Button label={strings.settings.usb} icon="usb" variant="ghost" onPress={() => save(DEFAULT_ADDRESS)} style={styles.flex} />
          <Button label={strings.settings.scan} icon="qrcode-scan" variant="ghost" onPress={() => router.push('/scan')} style={styles.flex} />
        </View>
      </Card>
    </>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
});
