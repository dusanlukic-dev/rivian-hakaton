import { DarkTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';

import { initApp } from '@/app-init';
import { AlertOverlays } from '@/components/AlertOverlays';
import { strings } from '@/config/strings';
import { useAuth } from '@/state/auth';
import { colors } from '@/theme/colors';

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
  // Until the saved login is read the app shows only the dark background (no login-screen flash). Then the guards
  // pick the side: no token → the login screen; a token → the app. A 401 anywhere drops the token (api/client.ts).
  const ready = useAuth((a) => a.ready);
  const signedIn = useAuth((a) => a.token !== null);

  return (
    <ThemeProvider value={navTheme}>
      <View style={styles.root}>
        <StatusBar style="light" />
        {ready ? (
          <Stack
            screenOptions={{
              headerStyle: { backgroundColor: colors.card },
              headerTintColor: colors.foreground,
              contentStyle: { backgroundColor: colors.background },
            }}>
            {/* Explicit redirects: without them the router falls back to any open route (it picked the QR scanner). */}
            <Stack.Protected guard={signedIn} redirectTo="/login">
              <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
              <Stack.Screen name="trip/[id]" options={{ title: strings.summary.title }} />
            </Stack.Protected>
            <Stack.Protected guard={!signedIn} redirectTo="/">
              <Stack.Screen name="login" options={{ headerShown: false }} />
            </Stack.Protected>
            <Stack.Screen name="scan" options={{ title: strings.scan.title, presentation: 'modal' }} />
          </Stack>
        ) : null}
        {ready && signedIn ? <AlertOverlays /> : null}
      </View>
    </ThemeProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
});
