import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Keyboard, StyleSheet, View, type TextInputInstance } from 'react-native';
import Animated, { FadeIn, FadeOut, LinearTransition } from 'react-native-reanimated';

import { ApiError, api } from '@/api/client';
import { Banner, Button, Card, FULL_EDGES, Icon, Screen, TextField, TextLink, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { errorText } from '@/lib/format';
import { signedIn } from '@/state/auth';
import { useSettings } from '@/state/settings';
import { colors } from '@/theme/colors';

type Mode = 'login' | 'register';
type FieldErrors = { username?: string; password?: string };
type FormError = { text: string; unreachable: boolean };

/** docs/API.md §5 RegisterIn: 3–32 of a-z, 0-9, ".", "_", "-" (the server lowercases it). Password 6–128. */
const USERNAME = /^[a-z0-9._-]{3,32}$/i;
const MIN_PASSWORD = 6;
const layout = LinearTransition.duration(200);

/**
 * Shown whenever there is no token (root layout guard); logging in or registering switches to the app.
 * Nothing about the car computer here: the address is a setup detail. It only shows up as "Change address" when
 * the server can't be reached.
 */
export default function LoginScreen() {
  const address = useSettings((s) => s.address);
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const nameRef = useRef<TextInputInstance>(null);
  const passwordRef = useRef<TextInputInstance>(null);

  const registering = mode === 'register';

  // Back from the connection screen with a new address: the old "can't reach" message no longer applies.
  useFocusEffect(
    useCallback(() => {
      setError((e) => (e?.unreachable ? null : e));
    }, []),
  );

  function check(): FieldErrors {
    const user = username.trim();
    const out: FieldErrors = {};
    if (!user) out.username = strings.auth.needUsername;
    else if (registering && !USERNAME.test(user)) out.username = strings.auth.badUsername;
    if (!password) out.password = strings.auth.needPassword;
    else if (registering && password.length < MIN_PASSWORD) out.password = strings.auth.shortPassword;
    return out;
  }

  async function submit() {
    if (busy) return;
    const problems = check();
    setFieldErrors(problems);
    if (problems.username || problems.password) return;
    Keyboard.dismiss();
    setBusy(true);
    setError(null);
    const user = username.trim();
    try {
      const out = registering
        ? await api.register(address, { username: user, password, display_name: name.trim() || null })
        : await api.login(address, { username: user, password });
      signedIn(out); // the root layout's guard fades this screen out and the app in
    } catch (e) {
      setError(describe(e, user, address));
      setBusy(false);
    }
  }

  function switchMode() {
    setMode(registering ? 'login' : 'register');
    setError(null);
    setFieldErrors({});
  }

  return (
    <Screen edges={FULL_EDGES} contentStyle={styles.content}>
      <Animated.View layout={layout} style={styles.brand}>
        <View style={styles.logo}>
          <Icon name="steering" size={40} color={colors.foreground} />
        </View>
        <Txt size="xs" tone="subtle" weight="800" style={styles.kicker}>
          {strings.appName.toUpperCase()}
        </Txt>
        <Txt size="xl" style={styles.center}>
          {registering ? strings.auth.registerTitle : strings.auth.loginTitle}
        </Txt>
        <Txt size="sm" tone="muted" style={styles.center}>
          {registering ? strings.auth.registerSubtitle : strings.auth.loginSubtitle}
        </Txt>
      </Animated.View>

      {error ? (
        <Animated.View entering={FadeIn.duration(200)} exiting={FadeOut.duration(150)} layout={layout}>
          <Banner
            icon={error.unreachable ? 'lan-disconnect' : 'alert-circle-outline'}
            text={error.text}
            color={colors.destructive}
            action={error.unreachable ? { label: strings.auth.changeAddress, onPress: () => router.push('/connection') } : undefined}
          />
        </Animated.View>
      ) : null}

      <Animated.View layout={layout}>
        <Card>
          <TextField
            label={strings.auth.username}
            placeholder={strings.auth.usernamePlaceholder}
            hint={registering ? strings.auth.usernameHint : undefined}
            error={fieldErrors.username}
            value={username}
            onChangeText={(text) => {
              setUsername(text);
              if (fieldErrors.username) setFieldErrors((f) => ({ ...f, username: undefined }));
            }}
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="username"
            textContentType="username"
            returnKeyType="next"
            submitBehavior="submit"
            onSubmitEditing={() => (registering ? nameRef : passwordRef).current?.focus()}
          />
          {registering ? (
            <Animated.View entering={FadeIn.duration(200)} exiting={FadeOut.duration(120)}>
              <TextField
                ref={nameRef}
                label={strings.auth.name}
                optional
                placeholder={strings.auth.namePlaceholder}
                hint={strings.auth.nameHint}
                value={name}
                onChangeText={setName}
                autoCapitalize="words"
                autoComplete="name"
                textContentType="name"
                returnKeyType="next"
                submitBehavior="submit"
                onSubmitEditing={() => passwordRef.current?.focus()}
              />
            </Animated.View>
          ) : null}
          <Animated.View layout={layout}>
            <TextField
              ref={passwordRef}
              label={strings.auth.password}
              secure
              hint={registering ? strings.auth.passwordHint : undefined}
              error={fieldErrors.password}
              value={password}
              onChangeText={(text) => {
                setPassword(text);
                if (fieldErrors.password) setFieldErrors((f) => ({ ...f, password: undefined }));
              }}
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete={registering ? 'new-password' : 'current-password'}
              textContentType={registering ? 'newPassword' : 'password'}
              returnKeyType="go"
              onSubmitEditing={() => void submit()}
            />
          </Animated.View>
        </Card>
      </Animated.View>

      <Animated.View layout={layout} style={styles.actions}>
        <Button
          label={registering ? strings.auth.register : strings.auth.login}
          icon={registering ? 'account-plus' : 'login'}
          loading={busy}
          onPress={() => void submit()}
        />
        <View style={styles.switchRow}>
          <Txt tone="muted">{registering ? strings.auth.haveAccount : strings.auth.newHere}</Txt>
          <TextLink label={registering ? strings.auth.toLogin : strings.auth.toRegister} onPress={switchMode} />
        </View>
      </Animated.View>
    </Screen>
  );
}

function describe(e: unknown, username: string, address: string): FormError {
  if (e instanceof ApiError) {
    if (e.status === 0) return { text: strings.auth.unreachable(address), unreachable: true };
    if (e.status === 401) return { text: strings.auth.wrong, unreachable: false };
    if (e.status === 409) return { text: strings.auth.taken(username.toLowerCase()), unreachable: false };
  }
  return { text: errorText(e), unreachable: false };
}

const styles = StyleSheet.create({
  content: { flexGrow: 1, justifyContent: 'center', paddingVertical: 24 },
  brand: { alignItems: 'center', gap: 6, paddingBottom: 8 },
  logo: {
    width: 76,
    height: 76,
    borderRadius: 38,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.secondary,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: 8,
  },
  kicker: { letterSpacing: 2 },
  center: { textAlign: 'center' },
  actions: { gap: 16 },
  switchRow: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 6 },
});
