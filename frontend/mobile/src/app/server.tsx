import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { normalizeServerAddress } from '@/api/address';
import { api } from '@/api/client';
import { ServerStatusPill } from '@/components/server';
import { Button, Card, Chevron, Divider, Icon, ListRow, Screen, SectionLabel, STACK_EDGES, TextField, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { errorText } from '@/lib/format';
import { DEFAULT_SERVER_ADDRESS, settingsStore, useSettings } from '@/state/settings';
import { colors } from '@/theme/colors';

type Result = { ok: boolean; text: string };

/**
 * The server's address (accounts, history, drive reports): the laptop's IP and port over the hotspot, localhost over
 * USB, or a public https link (e.g. an ngrok tunnel). Opened from the gear on the login screen, from Settings, or from
 * "Change address" when login can't reach the server. Saving switches every server call right away; app-init.ts then
 * re-checks the saved login on the new server.
 */
export default function ServerScreen() {
  const saved = useSettings((s) => s.serverAddress);
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

  // Fresh reachability for the status pill. Silent: the pill keeps its last value until the answer arrives.
  useEffect(() => {
    api.serverHealth(saved).catch(() => {});
  }, [saved]);

  function save(value: string, done?: string) {
    const address = normalizeServerAddress(value);
    if (!address) {
      setResult({ ok: false, text: strings.server.invalid });
      return;
    }
    setSeen(address); // our own change: keep the result line below
    settingsStore.set({ serverAddress: address });
    setDraft(address);
    setResult({ ok: true, text: done ?? strings.server.saved(address) });
  }

  async function test() {
    const address = normalizeServerAddress(draft);
    if (!address) {
      setResult({ ok: false, text: strings.server.invalid });
      return;
    }
    setTesting(true);
    const started = Date.now();
    try {
      await api.serverHealth(address);
      setResult({ ok: true, text: strings.server.testOk(Date.now() - started) });
    } catch (e) {
      setResult({ ok: false, text: errorText(e) });
    } finally {
      setTesting(false);
    }
  }

  return (
    <Screen edges={STACK_EDGES}>
      <Txt size="sm" tone="muted">
        {strings.server.intro}
      </Txt>

      <Card flush>
        <ListRow icon="server-network" title={saved} subtitle={strings.server.current} right={<ServerStatusPill address={saved} />} />
      </Card>

      <Card>
        <TextField
          label={strings.server.address}
          placeholder={strings.server.addressPlaceholder}
          hint={strings.server.addressHint}
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
            label={strings.server.test}
            icon="lan-connect"
            variant="secondary"
            loading={testing}
            onPress={() => void test()}
            style={styles.flex}
          />
          <Button
            label={strings.server.save}
            icon="content-save"
            disabled={draft.trim() === saved}
            onPress={() => save(draft)}
            style={styles.flex}
          />
        </View>
      </Card>

      <SectionLabel>{strings.server.quickSetup}</SectionLabel>
      <Card flush>
        <ListRow
          icon="qrcode-scan"
          title={strings.server.scanTitle}
          subtitle={strings.server.scanBody}
          right={<Chevron />}
          onPress={() => router.push('/scan')}
        />
        <Divider />
        <ListRow
          icon="usb"
          title={strings.server.usbTitle}
          subtitle={strings.server.usbBody}
          right={saved === DEFAULT_SERVER_ADDRESS ? <Icon name="check-circle" size={22} color={colors.ok} /> : null}
          onPress={() => save(DEFAULT_SERVER_ADDRESS, strings.server.usbDone)}
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
