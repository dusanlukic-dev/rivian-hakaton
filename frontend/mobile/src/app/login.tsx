import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { ApiError, api } from '@/api/client';
import { ConnectionCard } from '@/components/connection';
import { StatusPill } from '@/components/dashboard';
import { Banner, Button, Card, Icon, Screen, TextField, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { errorText } from '@/lib/format';
import { signedIn } from '@/state/auth';
import { useLive } from '@/state/live';
import { useSettings } from '@/state/settings';
import { colors, radius } from '@/theme/colors';

type Mode = 'login' | 'register';

/** Shown whenever there is no token (root layout guard). Logging in or registering switches to the app. */
export default function LoginScreen() {
  const address = useSettings((s) => s.address);
  const ready = useSettings((s) => s.ready);
  const connected = useLive((s) => s.status === 'open');
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editAddress, setEditAddress] = useState(false);

  const registering = mode === 'register';
  const canSubmit = username.trim().length > 0 && password.length > 0 && !busy;

  async function submit() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    const user = username.trim();
    try {
      const out = registering
        ? await api.register(address, { username: user, password, display_name: name.trim() || null })
        : await api.login(address, { username: user, password });
      signedIn(out); // the root layout's guard swaps this screen for the app
    } catch (e) {
      setError(messageFor(e, user));
      setBusy(false);
    }
  }

  function switchMode() {
    setMode(registering ? 'login' : 'register');
    setError(null);
  }

  return (
    <Screen>
      <View style={styles.brand}>
        <View style={styles.logo}>
          <Icon name="steering" size={44} color={colors.foreground} />
        </View>
        <Txt size="xs" tone="subtle" weight="800" style={styles.kicker}>
          {strings.appName.toUpperCase()}
        </Txt>
        <Txt size="xxl">{registering ? strings.auth.register : strings.auth.title}</Txt>
        <Txt size="sm" tone="muted" style={styles.center}>
          {strings.auth.subtitle}
        </Txt>
      </View>

      {error ? <Banner icon="alert-circle-outline" text={error} color={colors.destructive} /> : null}

      <Card>
        <TextField
          label={strings.auth.username}
          hint={registering ? strings.auth.usernameHint : undefined}
          value={username}
          onChangeText={setUsername}
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="username"
          textContentType="username"
          returnKeyType="next"
          placeholder="ana"
        />
        {registering ? (
          <TextField
            label={strings.auth.name}
            hint={strings.auth.nameHint}
            value={name}
            onChangeText={setName}
            autoCapitalize="words"
            autoComplete="name"
            returnKeyType="next"
            placeholder="Ana Anić"
          />
        ) : null}
        <TextField
          label={strings.auth.password}
          hint={registering ? strings.auth.passwordHint : undefined}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete={registering ? 'new-password' : 'current-password'}
          returnKeyType="go"
          onSubmitEditing={() => void submit()}
        />
      </Card>

      <Button
        big
        label={registering ? strings.auth.register : strings.auth.login}
        icon={registering ? 'account-plus' : 'login'}
        loading={busy}
        disabled={!canSubmit}
        onPress={() => void submit()}
      />
      <Button variant="ghost" label={registering ? strings.auth.toLogin : strings.auth.toRegister} onPress={switchMode} />

      <Card style={styles.carCard}>
        <View style={styles.row}>
          <Icon name="car-connected" size={22} color={colors.muted} />
          <View style={styles.flex}>
            <Txt size="sm" weight="700">
              {strings.auth.carComputer}
            </Txt>
            <Txt size="xs" tone="muted">
              {address}
            </Txt>
          </View>
          <StatusPill />
        </View>
        {!connected && !editAddress ? (
          <Txt size="xs" tone="subtle">
            {strings.auth.offline}
          </Txt>
        ) : null}
        <Button
          variant="secondary"
          icon={editAddress ? 'check' : 'pencil'}
          label={editAddress ? strings.auth.hide : strings.auth.change}
          onPress={() => setEditAddress((v) => !v)}
        />
      </Card>
      {editAddress && ready ? <ConnectionCard key={address} saved={address} label={false} /> : null}
    </Screen>
  );
}

function messageFor(e: unknown, username: string): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return strings.auth.wrong;
    if (e.status === 409) return strings.auth.taken(username.toLowerCase());
  }
  return errorText(e);
}

const styles = StyleSheet.create({
  brand: { alignItems: 'center', gap: 6, paddingTop: 24, paddingBottom: 8 },
  logo: {
    width: 84,
    height: 84,
    borderRadius: 42,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.secondary,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: 6,
  },
  kicker: { letterSpacing: 2 },
  center: { textAlign: 'center' },
  carCard: { gap: 10, borderRadius: radius.lg },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  flex: { flex: 1 },
});
