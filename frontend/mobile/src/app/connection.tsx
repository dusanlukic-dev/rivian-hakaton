import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { normalizeAddress } from '@/api/address';
import { api } from '@/api/client';
import { StatusPill } from '@/components/dashboard';
import { Button, Card, Chevron, Divider, Icon, ListRow, Screen, SectionLabel, STACK_EDGES, TextField, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { errorText } from '@/lib/format';
import { DEFAULT_ADDRESS, settingsStore, useSettings } from '@/state/settings';
import { colors } from '@/theme/colors';

type Result = { ok: boolean; text: string };

/**
 * The car computer's address (backend "host:port"). A setup/debug tool: opened from Settings, or from the login
 * screen's "Change address" when the server can't be reached. Saving reconnects the live socket right away
 * (state/live.ts follows the settings store).
 */
export default function ConnectionScreen() {
  const saved = useSettings((s) => s.address);
  const [draft, setDraft] = useState(saved);
  const [seen, setSeen] = useState(saved);
  const [result, setResult] = useState<Result | null>(null);
  const [testing, setTesting] = useState(false);

  // The address changed elsewhere (a QR scan): show it in the field.
  if (seen !== saved) {
    setSeen(saved);
    setDraft(saved);
    setResult(null);
  }

  function save(value: string, done?: string) {
    const address = normalizeAddress(value);
    if (!address) {
      setResult({ ok: false, text: strings.carComputer.invalid });
      return;
    }
    setSeen(address); // our own change: keep the result line below
    settingsStore.set({ address });
    setDraft(address);
    setResult({ ok: true, text: done ?? strings.carComputer.saved(address) });
  }

  async function test() {
    const address = normalizeAddress(draft);
    if (!address) {
      setResult({ ok: false, text: strings.carComputer.invalid });
      return;
    }
    setTesting(true);
    const started = Date.now();
    try {
      await api.health(address);
      setResult({ ok: true, text: strings.carComputer.testOk(Date.now() - started) });
    } catch (e) {
      setResult({ ok: false, text: errorText(e) });
    } finally {
      setTesting(false);
    }
  }

  return (
    <Screen edges={STACK_EDGES}>
      <Txt size="sm" tone="muted">
        {strings.carComputer.intro}
      </Txt>

      <Card flush>
        <ListRow icon="car-connected" title={saved} subtitle={strings.carComputer.current} right={<StatusPill />} />
      </Card>

      <Card>
        <TextField
          label={strings.carComputer.address}
          placeholder={strings.carComputer.addressPlaceholder}
          hint={strings.carComputer.addressHint}
          value={draft}
          onChangeText={(text) => {
            setDraft(text);
            setResult(null);
          }}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          returnKeyType="done"
          onSubmitEditing={() => save(draft)}
        />
        {result ? (
          <View style={styles.result}>
            <Icon
              name={result.ok ? 'check-circle' : 'alert-circle-outline'}
              size={18}
              color={result.ok ? colors.ok : colors.destructive}
            />
            <Txt size="sm" style={[styles.flex, { color: result.ok ? colors.ok : colors.destructive }]}>
              {result.text}
            </Txt>
          </View>
        ) : null}
        <View style={styles.buttons}>
          <Button
            label={strings.carComputer.test}
            icon="lan-connect"
            variant="secondary"
            loading={testing}
            onPress={() => void test()}
            style={styles.flex}
          />
          <Button
            label={strings.carComputer.save}
            icon="content-save"
            disabled={draft.trim() === saved}
            onPress={() => save(draft)}
            style={styles.flex}
          />
        </View>
      </Card>

      <SectionLabel>{strings.carComputer.quickSetup}</SectionLabel>
      <Card flush>
        <ListRow
          icon="qrcode-scan"
          title={strings.carComputer.scanTitle}
          subtitle={strings.carComputer.scanBody}
          right={<Chevron />}
          onPress={() => router.push('/scan')}
        />
        <Divider />
        <ListRow
          icon="usb"
          title={strings.carComputer.usbTitle}
          subtitle={strings.carComputer.usbBody}
          right={saved === DEFAULT_ADDRESS ? <Icon name="check-circle" size={22} color={colors.ok} /> : null}
          onPress={() => save(DEFAULT_ADDRESS, strings.carComputer.usbDone)}
        />
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  result: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  buttons: { flexDirection: 'row', alignItems: 'center', gap: 8 },
});
