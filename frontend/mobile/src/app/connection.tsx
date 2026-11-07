import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { openAppSettings, openBluetoothSettings } from '@/alerts/notifications';
import { normalizeAddress, normalizeServerAddress } from '@/api/address';
import { requestCarLinkPermission, type NearbyCar } from '@/api/carlink';
import { api } from '@/api/client';
import { StatusPill } from '@/components/dashboard';
import { Button, Card, Chevron, Divider, Icon, ListRow, Screen, SectionLabel, STACK_EDGES, TextField, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { errorText } from '@/lib/format';
import { connectToCar, disconnectCar, forgetCar, reconnectCar, retryCarLink, useLive } from '@/state/live';
import { DEFAULT_ADDRESS, settingsStore, useSettings, type CarLinkMode } from '@/state/settings';
import { colors } from '@/theme/colors';

type Result = { ok: boolean; text: string };

/**
 * How the phone reaches the car computer: Bluetooth (docs/BLUETOOTH.md, the default) or Wi-Fi/USB with an address.
 * A setup screen, opened from Settings or from the Drive tab when the car can't be reached. Every change reconnects
 * the live link right away (state/live.ts follows the settings store).
 */
export default function ConnectionScreen() {
  const mode = useSettings((s) => s.carLink);

  const choose = (carLink: CarLinkMode) => {
    if (carLink !== settingsStore.get().carLink) settingsStore.set({ carLink });
  };
  const check = <Icon name="check-circle" size={22} color={colors.ok} />;

  return (
    <Screen edges={STACK_EDGES}>
      <Txt size="sm" tone="muted">
        {strings.carLink.intro}
      </Txt>

      <SectionLabel>{strings.carLink.mode}</SectionLabel>
      <Card flush>
        <ListRow
          icon="bluetooth"
          title={strings.carLink.bluetooth}
          subtitle={strings.carLink.bluetoothHint}
          right={mode === 'bluetooth' ? check : null}
          onPress={() => choose('bluetooth')}
        />
        <Divider />
        <ListRow
          icon="wifi"
          title={strings.carLink.wifi}
          subtitle={strings.carLink.wifiHint}
          right={mode === 'wifi' ? check : null}
          onPress={() => choose('wifi')}
        />
      </Card>

      {mode === 'bluetooth' ? <BluetoothCar /> : <WifiAddress />}
    </Screen>
  );
}

/** The remembered car, what the link is doing, the one action that helps, and the cars nearby to pick from. */
function BluetoothCar() {
  const info = useLive((s) => s.carLink);
  const nearby = useLive((s) => s.nearbyCars);
  const carName = useSettings((s) => s.carName);
  const carDeviceId = useSettings((s) => s.carDeviceId);
  const carScanName = useSettings((s) => s.carScanName);
  const auto = useSettings((s) => s.carAuto);
  const serverAddress = useSettings((s) => s.serverAddress);
  const [blocked, setBlocked] = useState(false);

  const phase = info?.phase ?? 'choose';
  const linked = phase === 'connected' || phase === 'car-offline';
  const remembered = carDeviceId !== null;
  const name = info?.hello?.car ?? carName ?? strings.carLink.noCar;
  const offered = info?.hello?.server_url ? normalizeServerAddress(info.hello.server_url) : null;
  const icon = linked ? 'bluetooth-connect' : phase === 'off' ? 'bluetooth-off' : 'bluetooth';
  const mine = (car: NearbyCar) =>
    remembered && (car.id === carDeviceId || (carScanName !== null && car.name === carScanName));

  async function allow() {
    const result = await requestCarLinkPermission();
    setBlocked(result === 'blocked');
    retryCarLink();
  }

  return (
    <>
      <SectionLabel>{strings.carLink.car}</SectionLabel>
      <Card flush>
        <ListRow
          icon={icon}
          iconColor={linked ? colors.ok : colors.muted}
          title={name}
          subtitle={blocked ? strings.carLink.blocked : strings.carLink.phase[phase]}
          right={<StatusPill />}
        />
        {offered && offered !== serverAddress ? (
          <>
            <Divider />
            <ListRow
              icon="server-network"
              title={strings.carLink.useServer}
              subtitle={strings.carLink.serverOffer(offered)}
              right={<Chevron />}
              onPress={() => settingsStore.set({ serverAddress: offered })}
            />
          </>
        ) : null}
        {carDeviceId ? (
          <>
            <Divider />
            <ListRow icon="link-variant-off" title={strings.carLink.forget} subtitle={strings.carLink.forgetHint} onPress={forgetCar} />
          </>
        ) : null}
      </Card>

      {phase === 'no-permission' ? (
        blocked ? (
          <Button label={strings.carLink.openAppSettings} icon="open-in-new" onPress={() => void openAppSettings()} />
        ) : (
          <Button label={strings.carLink.allow} icon="bluetooth" onPress={() => void allow()} />
        )
      ) : phase === 'off' ? (
        <Button label={strings.carLink.openBluetooth} icon="bluetooth-settings" onPress={() => void openBluetoothSettings()} />
      ) : linked ? (
        <Button label={strings.carLink.disconnect} icon="bluetooth-off" variant="secondary" onPress={disconnectCar} />
      ) : remembered && !auto ? (
        <Button label={strings.carLink.connectTo(carName ?? strings.carLink.yourCar)} icon="bluetooth-connect" onPress={reconnectCar} />
      ) : phase === 'searching' ? (
        <Button label={strings.carLink.searchAgain} icon="bluetooth-connect" variant="secondary" onPress={retryCarLink} />
      ) : null}

      {phase === 'choose' || phase === 'searching' ? (
        <>
          <SectionLabel>{strings.carLink.nearby}</SectionLabel>
          <Card flush>
            {nearby.length === 0 ? (
              <ListRow
                icon="radar"
                title={strings.carLink.nearbyEmpty}
                subtitle={strings.carLink.nearbyEmptyHint}
                right={<ActivityIndicator color={colors.muted} />}
              />
            ) : (
              nearby.map((car, i) => (
                <View key={car.id}>
                  {i > 0 ? <Divider /> : null}
                  <ListRow
                    icon="car"
                    title={(mine(car) ? carName : null) ?? car.name ?? strings.carLink.unnamed}
                    subtitle={strings.carLink.signal(car.rssi, mine(car))}
                    right={<Button size="sm" label={strings.carLink.connect} onPress={() => connectToCar(car)} />}
                  />
                </View>
              ))
            )}
          </Card>
        </>
      ) : null}
    </>
  );
}

/** The car computer's "host:port" for the Wi-Fi/USB link. */
function WifiAddress() {
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
      await api.wifiHealth(address);
      setResult({ ok: true, text: strings.carComputer.testOk(Date.now() - started) });
    } catch (e) {
      setResult({ ok: false, text: errorText(e) });
    } finally {
      setTesting(false);
    }
  }

  return (
    <>
      <SectionLabel>{strings.carComputer.wifiSection}</SectionLabel>
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
    </>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  result: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  buttons: { flexDirection: 'row', alignItems: 'center', gap: 8 },
});
