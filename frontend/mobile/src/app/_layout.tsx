import { DarkTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import { KeyboardProvider } from 'react-native-keyboard-controller';

import { initApp } from '@/app-init';
import { AlertOverlays } from '@/components/AlertOverlays';
import { strings } from '@/config/strings';
import { useAuth } from '@/state/auth';
import { colors } from '@/theme/colors';

// The native splash stays up until the boot check is done (app-init.ts), then fades into the first real screen.
void SplashScreen.preventAutoHideAsync().catch(() => {});
SplashScreen.setOptions({ duration: 250, fade: true });

const navTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    primary: colors.primary,
    background: colors.background,
    card: colors.card,
    text: colors.foreground,
    border: colors.border,
    notification: colors.alarm,
  },
};

export default function RootLayout() {
  useEffect(() => {
    initApp();
  }, []);
  // `ready` = the saved login was read and checked with the server (or the server didn't answer in time). Until
  // then nothing renders behind the splash. Then the guards pick the side: no token → login; a token → the app.
  // A 401 anywhere later drops the token (api/client.ts) and the guard switches to the login screen.
  const ready = useAuth((a) => a.ready);
  const signedIn = useAuth((a) => a.token !== null);

  useEffect(() => {
    if (ready) SplashScreen.hide();
  }, [ready]);

  return (
    <ThemeProvider value={navTheme}>
      <KeyboardProvider>
        <View style={styles.root}>
          <StatusBar style="light" />
          {ready ? (
            <Stack
              screenOptions={{
                headerStyle: { backgroundColor: colors.card },
                headerTintColor: colors.foreground,
                headerShadowVisible: false,
                contentStyle: { backgroundColor: colors.background },
              }}>
              {/* Explicit redirects: without them the router falls back to any open route (it picked the QR scanner). */}
              <Stack.Protected guard={signedIn} redirectTo="/login">
                <Stack.Screen name="(tabs)" options={{ headerShown: false, animation: 'fade' }} />
                <Stack.Screen name="trip/[id]" options={{ title: strings.summary.title }} />
              </Stack.Protected>
              <Stack.Protected guard={!signedIn} redirectTo="/">
                <Stack.Screen name="login" options={{ headerShown: false, animation: 'fade' }} />
              </Stack.Protected>
              {/* Reachable signed in (Settings) and signed out (login → "Change address"). */}
              <Stack.Screen name="connection" options={{ title: strings.carComputer.title }} />
              <Stack.Screen name="scan" options={{ title: strings.scan.title, presentation: 'modal' }} />
            </Stack>
          ) : null}
          {ready && signedIn ? <AlertOverlays /> : null}
        </View>
      </KeyboardProvider>
    </ThemeProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
});
