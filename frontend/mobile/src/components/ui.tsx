import { MaterialCommunityIcons } from '@expo/vector-icons';
import type { ComponentProps, ReactElement, ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
  type RefreshControlProps,
  type StyleProp,
  type TextInputProps,
  type TextProps,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors, radius } from '@/theme/colors';

export type IconName = ComponentProps<typeof MaterialCommunityIcons>['name'];

export function Icon(props: ComponentProps<typeof MaterialCommunityIcons>) {
  return <MaterialCommunityIcons {...props} />;
}

type Tone = 'default' | 'muted' | 'subtle' | 'danger' | 'inverse';
type Size = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl' | 'display';
type Weight = '400' | '500' | '600' | '700' | '800' | '900';

const SIZES: Record<Size, { fontSize: number; lineHeight: number }> = {
  xs: { fontSize: 11, lineHeight: 15 },
  sm: { fontSize: 13, lineHeight: 18 },
  md: { fontSize: 15, lineHeight: 21 },
  lg: { fontSize: 18, lineHeight: 24 },
  xl: { fontSize: 26, lineHeight: 32 },
  xxl: { fontSize: 40, lineHeight: 46 },
  display: { fontSize: 76, lineHeight: 82 },
};

const TONES: Record<Tone, string> = {
  default: colors.foreground,
  muted: colors.muted,
  subtle: colors.subtle,
  danger: colors.destructive,
  inverse: colors.background,
};

export function Txt({
  tone = 'default',
  size = 'md',
  weight,
  style,
  ...props
}: TextProps & { tone?: Tone; size?: Size; weight?: Weight }) {
  const heavy = size === 'xl' || size === 'xxl' || size === 'display';
  return <Text {...props} style={[{ color: TONES[tone], fontWeight: weight ?? (heavy ? '800' : '400') }, SIZES[size], style]} />;
}

export function Screen({
  children,
  refreshControl,
}: {
  children: ReactNode;
  refreshControl?: ReactElement<RefreshControlProps>;
}) {
  return (
    <SafeAreaView style={styles.screen} edges={['top', 'left', 'right']}>
      <ScrollView contentContainerStyle={styles.content} refreshControl={refreshControl} keyboardShouldPersistTaps="handled">
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function ScreenHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <View style={styles.header}>
      <View style={styles.flex}>
        <Txt size="xl">{title}</Txt>
        {subtitle ? (
          <Txt size="sm" tone="muted">
            {subtitle}
          </Txt>
        ) : null}
      </View>
      {right}
    </View>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function SectionLabel({ children }: { children: string }) {
  return (
    <Txt size="xs" tone="subtle" weight="700" style={styles.sectionLabel}>
      {children.toUpperCase()}
    </Txt>
  );
}

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';
const VARIANTS: Record<Variant, { bg: string; fg: string; border: string }> = {
  primary: { bg: colors.primary, fg: colors.primaryForeground, border: colors.primary },
  secondary: { bg: colors.secondary, fg: colors.foreground, border: colors.border },
  danger: { bg: 'transparent', fg: colors.destructive, border: colors.destructive },
  ghost: { bg: 'transparent', fg: colors.foreground, border: 'transparent' },
};

export function Button({
  label,
  onPress,
  variant = 'primary',
  icon,
  loading,
  disabled,
  big,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: Variant;
  icon?: IconName;
  loading?: boolean;
  disabled?: boolean;
  big?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const v = VARIANTS[variant];
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled || loading}
      android_ripple={{ color: 'rgba(255,255,255,0.12)' }}
      style={({ pressed }) => [
        styles.button,
        big && styles.buttonBig,
        { backgroundColor: v.bg, borderColor: v.border, opacity: disabled ? 0.45 : pressed ? 0.85 : 1 },
        style,
      ]}>
      {loading ? (
        <ActivityIndicator color={v.fg} />
      ) : (
        <>
          {icon ? <Icon name={icon} size={big ? 22 : 18} color={v.fg} /> : null}
          <Text style={[styles.buttonText, big && styles.buttonTextBig, { color: v.fg }]}>{label}</Text>
        </>
      )}
    </Pressable>
  );
}

export function TextField({ label, hint, style, ...props }: TextInputProps & { label: string; hint?: string }) {
  return (
    <View style={styles.field}>
      <Txt size="sm" tone="muted" weight="600">
        {label}
      </Txt>
      <TextInput placeholderTextColor={colors.subtle} selectionColor={colors.primary} {...props} style={[styles.input, style]} />
      {hint ? (
        <Txt size="xs" tone="subtle">
          {hint}
        </Txt>
      ) : null}
    </View>
  );
}

export function ToggleRow({
  icon,
  label,
  value,
  onValueChange,
}: {
  icon: IconName;
  label: string;
  value: boolean;
  onValueChange: (value: boolean) => void;
}) {
  return (
    <View style={styles.row}>
      <Icon name={icon} size={20} color={colors.muted} />
      <Txt style={styles.flex}>{label}</Txt>
      <Switch
        value={value}
        onValueChange={onValueChange}
        trackColor={{ false: colors.secondary, true: colors.ok }}
        thumbColor={colors.foreground}
      />
    </View>
  );
}

export function Pill({ label, color, icon }: { label: string; color: string; icon?: IconName }) {
  return (
    <View style={[styles.pill, { borderColor: color }]}>
      {icon ? <Icon name={icon} size={14} color={color} /> : <View style={[styles.dot, { backgroundColor: color }]} />}
      <Text style={[styles.pillText, { color }]}>{label}</Text>
    </View>
  );
}

export function Banner({ icon, text, color = colors.warn }: { icon: IconName; text: string; color?: string }) {
  return (
    <View style={[styles.banner, { borderColor: color }]}>
      <Icon name={icon} size={18} color={color} />
      <Txt size="sm" style={styles.flex}>
        {text}
      </Txt>
    </View>
  );
}

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: 16, paddingBottom: 40, gap: 16 },
  flex: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingTop: 4 },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: 16,
    gap: 12,
  },
  sectionLabel: { letterSpacing: 1.2, marginBottom: -4 },
  button: {
    minHeight: 48,
    borderRadius: radius.md,
    borderWidth: 1,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    overflow: 'hidden',
  },
  buttonBig: { minHeight: 60, borderRadius: radius.lg },
  buttonText: { fontSize: 15, fontWeight: '700' },
  buttonTextBig: { fontSize: 18 },
  field: { gap: 6 },
  input: {
    minHeight: 48,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.input,
    backgroundColor: colors.background,
    color: colors.foreground,
    paddingHorizontal: 14,
    fontSize: 16,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 44 },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: 1,
    borderRadius: radius.full,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  pillText: { fontSize: 12, fontWeight: '700' },
  dot: { width: 8, height: 8, borderRadius: 4 },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: 12,
    backgroundColor: colors.card,
  },
});
