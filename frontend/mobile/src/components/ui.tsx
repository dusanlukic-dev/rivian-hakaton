import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useState, type ComponentProps, type ReactElement, type ReactNode, type Ref } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
  type RefreshControlProps,
  type StyleProp,
  type TextInputInstance,
  type TextInputProps,
  type TextProps,
  type ViewStyle,
} from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import { SafeAreaView, type Edge } from 'react-native-safe-area-context';

import { strings } from '@/config/strings';
import { colors, radius, withAlpha } from '@/theme/colors';

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

/** Ripple for presses on dark surfaces (bounded to the pressed element, never a borderless circle). */
const RIPPLE = 'rgba(255,255,255,0.08)';

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

/** Tab screens: the tab bar owns the bottom edge. */
export const TAB_EDGES: readonly Edge[] = ['top', 'left', 'right'];
/** Stack screens under a header: keep content off the system navigation buttons. */
export const STACK_EDGES: readonly Edge[] = ['left', 'right', 'bottom'];
/** Full-screen pages without header or tab bar (login). */
export const FULL_EDGES: readonly Edge[] = ['top', 'left', 'right', 'bottom'];

/** Gap between a focused input and the top of the keyboard. */
const KEYBOARD_GAP = 24;

/**
 * Scrollable page inside the safe area. A focused input always scrolls above the keyboard
 * (react-native-keyboard-controller: with edge-to-edge, Android no longer resizes the window for it).
 */
export function Screen({
  children,
  refreshControl,
  edges = TAB_EDGES,
  contentStyle,
}: {
  children: ReactNode;
  refreshControl?: ReactElement<RefreshControlProps>;
  edges?: readonly Edge[];
  contentStyle?: StyleProp<ViewStyle>;
}) {
  return (
    <SafeAreaView style={styles.screen} edges={edges}>
      <KeyboardAwareScrollView
        bottomOffset={KEYBOARD_GAP}
        contentContainerStyle={[styles.content, contentStyle]}
        refreshControl={refreshControl}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>
        {children}
      </KeyboardAwareScrollView>
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

/** `flush`: no padding, for lists of `ListRow`s whose ripples should reach the card's edges. */
export function Card({ children, style, flush }: { children: ReactNode; style?: StyleProp<ViewStyle>; flush?: boolean }) {
  return <View style={[styles.card, flush && styles.cardFlush, style]}>{children}</View>;
}

export function SectionLabel({ children }: { children: string }) {
  return (
    <Txt size="xs" tone="subtle" weight="700" style={styles.sectionLabel}>
      {children.toUpperCase()}
    </Txt>
  );
}

/** Hairline between `ListRow`s, inset to line up with the row text (`inset={false}`: full width). */
export function Divider({ inset = true }: { inset?: boolean }) {
  return <View style={[styles.divider, inset && styles.dividerInset]} />;
}

/**
 * Settings-style row: icon, title, optional one-line explanation, something on the right (chevron, status, button).
 * Pressable when `onPress` is given.
 */
export function ListRow({
  icon,
  iconColor,
  title,
  subtitle,
  right,
  onPress,
}: {
  icon?: IconName;
  iconColor?: string;
  title: string;
  subtitle?: string;
  right?: ReactNode;
  onPress?: () => void;
}) {
  const body = (
    <>
      {icon ? (
        <View style={styles.rowIcon}>
          <Icon name={icon} size={20} color={iconColor ?? colors.muted} />
        </View>
      ) : null}
      <View style={styles.flex}>
        <Txt weight="600">{title}</Txt>
        {subtitle ? (
          <Txt size="sm" tone="muted">
            {subtitle}
          </Txt>
        ) : null}
      </View>
      {right}
    </>
  );
  if (!onPress) return <View style={styles.listRow}>{body}</View>;
  return (
    <Pressable accessibilityRole="button" onPress={onPress} android_ripple={{ color: RIPPLE }} style={styles.listRow}>
      {body}
    </Pressable>
  );
}

export function Chevron() {
  return <Icon name="chevron-right" size={22} color={colors.subtle} />;
}

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';
const VARIANTS: Record<Variant, { bg: string; fg: string; border: string; ripple: string }> = {
  primary: { bg: colors.primary, fg: colors.primaryForeground, border: colors.primary, ripple: 'rgba(0,0,0,0.12)' },
  secondary: { bg: colors.secondary, fg: colors.foreground, border: colors.border, ripple: 'rgba(255,255,255,0.12)' },
  danger: { bg: 'transparent', fg: colors.destructive, border: colors.destructive, ripple: withAlpha(colors.destructive, 0.16) },
  ghost: { bg: 'transparent', fg: colors.foreground, border: 'transparent', ripple: 'rgba(255,255,255,0.12)' },
};

type ButtonSize = 'sm' | 'md' | 'lg';
const BUTTON_SIZES: Record<ButtonSize, { height: number; padding: number; font: number; icon: number }> = {
  sm: { height: 36, padding: 14, font: 14, icon: 16 },
  md: { height: 48, padding: 16, font: 15, icon: 18 },
  lg: { height: 56, padding: 20, font: 17, icon: 20 },
};

/** One button style for the whole app: `md` everywhere, `sm` inside rows, `lg` only for the screen's main action. */
export function Button({
  label,
  onPress,
  variant = 'primary',
  size = 'md',
  icon,
  loading,
  disabled,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: Variant;
  size?: ButtonSize;
  icon?: IconName;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const v = VARIANTS[variant];
  const s = BUTTON_SIZES[size];
  const off = !!disabled && !loading;
  // A disabled primary becomes a quiet grey control instead of a washed-out white slab.
  const quiet = off && variant === 'primary';
  const fg = quiet ? colors.subtle : v.fg;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: off, busy: !!loading }}
      onPress={onPress}
      disabled={disabled || loading}
      android_ripple={{ color: v.ripple }}
      style={[
        styles.button,
        {
          minHeight: s.height,
          paddingHorizontal: s.padding,
          backgroundColor: quiet ? colors.secondary : v.bg,
          borderColor: quiet ? colors.secondary : v.border,
          opacity: off && !quiet ? 0.5 : 1,
        },
        style,
      ]}>
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <>
          {icon ? <Icon name={icon} size={s.icon} color={fg} /> : null}
          <Text style={[styles.buttonText, { color: fg, fontSize: s.font }]}>{label}</Text>
        </>
      )}
    </Pressable>
  );
}

/** Inline text action ("Create an account"). */
export function TextLink({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="link" onPress={onPress} hitSlop={12}>
      {({ pressed }) => (
        <Txt weight="700" style={[styles.link, pressed && styles.pressed]}>
          {label}
        </Txt>
      )}
    </Pressable>
  );
}

/**
 * Labelled input. Placeholders say what to type, never an example value. `secure` = password with a show/hide eye.
 * `error` replaces the hint in red. Pass `ref` to move focus from the previous field's Next key.
 */
export function TextField({
  label,
  hint,
  error,
  optional,
  secure,
  style,
  ref,
  onFocus,
  onBlur,
  ...props
}: TextInputProps & {
  label: string;
  hint?: string;
  error?: string;
  optional?: boolean;
  secure?: boolean;
  ref?: Ref<TextInputInstance>;
}) {
  const [focused, setFocused] = useState(false);
  const [hidden, setHidden] = useState(true);
  return (
    <View style={styles.field}>
      <View style={styles.labelRow}>
        <Txt size="sm" tone="muted" weight="600">
          {label}
        </Txt>
        {optional ? (
          <Txt size="xs" tone="subtle">
            {strings.common.optional}
          </Txt>
        ) : null}
      </View>
      <View style={[styles.inputBox, focused && styles.inputFocused, !!error && styles.inputError]}>
        <TextInput
          ref={ref}
          placeholderTextColor={colors.subtle}
          selectionColor={withAlpha(colors.primary, 0.35)}
          selectionHandleColor={colors.primary}
          cursorColor={colors.foreground}
          {...props}
          secureTextEntry={secure ? hidden : props.secureTextEntry}
          onFocus={(e) => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          style={[styles.input, style]}
        />
        {secure ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={hidden ? strings.common.showPassword : strings.common.hidePassword}
            onPress={() => setHidden((h) => !h)}
            hitSlop={8}
            style={styles.eye}>
            <Icon name={hidden ? 'eye-outline' : 'eye-off-outline'} size={20} color={colors.muted} />
          </Pressable>
        ) : null}
      </View>
      {error ? (
        <Txt size="xs" style={styles.errorText}>
          {error}
        </Txt>
      ) : hint ? (
        <Txt size="xs" tone="subtle">
          {hint}
        </Txt>
      ) : null}
    </View>
  );
}

/** The whole row toggles, like Android's own settings. */
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
    <Pressable
      accessibilityRole="switch"
      accessibilityState={{ checked: value }}
      onPress={() => onValueChange(!value)}
      style={styles.row}>
      <Icon name={icon} size={20} color={colors.muted} />
      <Txt style={styles.flex}>{label}</Txt>
      <Switch
        value={value}
        onValueChange={onValueChange}
        trackColor={{ false: colors.secondary, true: colors.ok }}
        thumbColor={colors.foreground}
      />
    </Pressable>
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

export function Banner({
  icon,
  text,
  color = colors.warn,
  action,
}: {
  icon: IconName;
  text: string;
  color?: string;
  action?: { label: string; onPress: () => void };
}) {
  return (
    <View style={[styles.banner, { borderColor: color, backgroundColor: withAlpha(color, 0.08) }]}>
      <View style={styles.bannerRow}>
        <Icon name={icon} size={18} color={color} />
        <Txt size="sm" style={styles.flex}>
          {text}
        </Txt>
      </View>
      {action ? <Button size="sm" variant="secondary" label={action.label} onPress={action.onPress} style={styles.bannerAction} /> : null}
    </View>
  );
}

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: 16, paddingBottom: 40, gap: 16 },
  flex: { flex: 1 },
  pressed: { opacity: 0.6 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingTop: 4 },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: 16,
    gap: 12,
  },
  cardFlush: { padding: 0, gap: 0, overflow: 'hidden' },
  sectionLabel: { letterSpacing: 1.2, marginBottom: -4 },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  dividerInset: { marginLeft: 66 },
  listRow: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: 16, paddingVertical: 14, minHeight: 64 },
  rowIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    backgroundColor: colors.secondary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  button: {
    borderRadius: radius.md,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    overflow: 'hidden',
  },
  buttonText: { fontWeight: '700' },
  link: { textDecorationLine: 'underline' },
  field: { gap: 6 },
  labelRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  inputBox: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.input,
    backgroundColor: colors.background,
  },
  inputFocused: { borderColor: 'rgba(255,255,255,0.5)' },
  inputError: { borderColor: colors.destructive },
  input: { flex: 1, minHeight: 46, color: colors.foreground, paddingHorizontal: 14, fontSize: 16 },
  eye: { width: 44, height: 46, alignItems: 'center', justifyContent: 'center' },
  errorText: { color: colors.destructive },
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
    gap: 10,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: 12,
  },
  bannerRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  bannerAction: { alignSelf: 'flex-start', marginLeft: 28 },
});
