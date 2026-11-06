import { DarkTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';

import { initApp } from '@/app-init';
import { AlertOverlays } from '@/components/AlertOverlays';
import { strings } from '@/config/strings';
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

  return (
    <ThemeProvider value={navTheme}>
      <View style={styles.root}>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.card },
            headerTintColor: colors.foreground,
            contentStyle: { backgroundColor: colors.background },
          }}>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="trip/[id]" options={{ title: strings.summary.title }} />
          <Stack.Screen name="scan" options={{ title: strings.scan.title, presentation: 'modal' }} />
        </Stack>
        <AlertOverlays />
      </View>
    </ThemeProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
});
