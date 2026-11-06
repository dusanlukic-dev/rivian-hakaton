import { Tabs } from 'expo-router';
import type { ColorValue } from 'react-native';

import { Icon, type IconName } from '@/components/ui';
import { strings } from '@/config/strings';
import { colors } from '@/theme/colors';

function TabIcon({ name, color, size }: { name: IconName; color: ColorValue; size: number }) {
  return <Icon name={name} color={color as string} size={size} />;
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: { backgroundColor: colors.card, borderTopColor: colors.border },
        tabBarActiveTintColor: colors.foreground,
        tabBarInactiveTintColor: colors.subtle,
        tabBarLabelStyle: { fontWeight: '600' },
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
