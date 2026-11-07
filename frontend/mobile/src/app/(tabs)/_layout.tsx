import { Tabs } from 'expo-router';
import type { BottomTabBarButtonProps } from 'expo-router/tabs';
import { Pressable, StyleSheet, type ColorValue } from 'react-native';

import { Icon, type IconName } from '@/components/ui';
import { strings } from '@/config/strings';
import { colors } from '@/theme/colors';

function TabIcon({ name, color, size }: { name: IconName; color: ColorValue; size: number }) {
  return <Icon name={name} color={color as string} size={size} />;
}

/**
 * The default tab button draws a big borderless ripple circle on Android. This one only dims while pressed.
 * The system navigation bar under the tab bar is transparent (app.json: expo-navigation-bar `enforceContrast: false`),
 * so the tab bar's own colour runs down behind the system buttons.
 */
function TabButton({ children, style, onPress, onLongPress, testID, 'aria-label': label, 'aria-selected': selected }: BottomTabBarButtonProps) {
  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityLabel={label}
      accessibilityState={{ selected: selected === true }}
      testID={testID}
      onPress={onPress}
      onLongPress={onLongPress}
      style={({ pressed }) => [style, pressed && styles.pressed]}>
      {children}
    </Pressable>
  );
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarButton: TabButton,
        tabBarHideOnKeyboard: true,
        tabBarStyle: styles.bar,
        tabBarActiveTintColor: colors.foreground,
        tabBarInactiveTintColor: colors.subtle,
        tabBarLabelStyle: styles.label,
      }}>
      <Tabs.Screen
        name="index"
        options={{ title: strings.tabs.drive, tabBarIcon: ({ color, size }) => <TabIcon name="steering" color={color} size={size} /> }}
      />
      <Tabs.Screen
        name="history"
        options={{ title: strings.tabs.history, tabBarIcon: ({ color, size }) => <TabIcon name="history" color={color} size={size} /> }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: strings.tabs.profile, tabBarIcon: ({ color, size }) => <TabIcon name="account-circle" color={color} size={size} /> }}
      />
      <Tabs.Screen
        name="settings"
        options={{ title: strings.tabs.settings, tabBarIcon: ({ color, size }) => <TabIcon name="cog" color={color} size={size} /> }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  // elevation 0: React Navigation's default elevation 8 throws a shadow up onto the screen content
  bar: { backgroundColor: colors.card, borderTopColor: colors.border, elevation: 0, shadowOpacity: 0 },
  label: { fontWeight: '600' },
  pressed: { opacity: 0.6 },
});
