import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { api } from '@/api/client';
import type { User } from '@/api/types';
import { Banner, Button, Card, Screen, ScreenHeader, SectionLabel, TextField, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { errorText, formatDateTime } from '@/lib/format';
import { authStore, setUser, signedOut, useAuth } from '@/state/auth';
import { liveStore } from '@/state/live';
import { settingsStore } from '@/state/settings';
import { colors } from '@/theme/colors';

/** The account (GET/PATCH /auth/me): name and emergency contact live on the server, plus log out. */
export default function ProfileScreen() {
  const user = useAuth((a) => a.user);

  // Pick up changes made elsewhere (another phone, Swagger). A 401 here logs out (api/client.ts).
  useFocusEffect(
    useCallback(() => {
      api
        .me(settingsStore.get().address)
        .then(setUser)
        .catch(() => {});
    }, []),
  );

  return (
    <Screen>
      <ScreenHeader title={strings.profile.title} subtitle={strings.profile.subtitle} />
      {/* keyed by the account, so the form starts from the account's saved values */}
      {user ? <ProfileForm key={user.user_id} user={user} /> : null}
    </Screen>
  );
}

function ProfileForm({ user }: { user: User }) {
  const [form, setForm] = useState({
    name: user.display_name,
    contactName: user.emergency_contact?.name ?? '',
    contactPhone: user.emergency_contact?.phone ?? '',
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [leaving, setLeaving] = useState(false);
  const update = (patch: Partial<typeof form>) => {
    setForm((f) => ({ ...f, ...patch }));
    setSaved(false);
  };
  const initials =
    form.name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('') || '?';

  async function save() {
    setSaving(true);
    setError(null);
    const phone = form.contactPhone.trim();
    try {
      const next = await api.updateMe(settingsStore.get().address, {
        display_name: form.name.trim() || user.username,
        emergency_contact: phone ? { name: form.contactName.trim() || strings.profile.contactFallback, phone } : null,
      });
      setSaved(true);
      setUser(next);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  async function logout() {
    setLeaving(true);
    const token = authStore.get().token;
    // Best effort: the server forgets the token; offline, the phone forgets it anyway.
    if (token) await api.logout(settingsStore.get().address).catch(() => {});
    liveStore.set({ summary: null }); // the next driver on this phone shouldn't see my last trip
    signedOut(); // the root layout's guard shows the login screen
  }

  return (
    <View style={styles.stack}>
      <View style={styles.avatarRow}>
        <View style={styles.avatar}>
          <Txt size="xl">{initials}</Txt>
        </View>
        <View style={styles.flex}>
          <Txt size="lg" weight="800">
            {user.display_name}
          </Txt>
          <Txt size="sm" tone="muted">
            @{user.username}
          </Txt>
          <Txt size="xs" tone="subtle">
            {strings.profile.memberSince(formatDateTime(user.created_at))}
          </Txt>
        </View>
      </View>

      {error ? <Banner icon="alert-circle-outline" text={error} color={colors.destructive} /> : null}

      <Card>
        <TextField
          label={strings.profile.name}
          value={form.name}
          onChangeText={(name) => update({ name })}
          autoCapitalize="words"
          placeholder={user.username}
        />
      </Card>

      <SectionLabel>{strings.profile.contact}</SectionLabel>
      <Card>
        <Txt size="sm" tone="muted">
          {strings.profile.contactHint}
        </Txt>
        <TextField
          label={strings.profile.contactName}
          value={form.contactName}
          onChangeText={(contactName) => update({ contactName })}
          autoCapitalize="words"
          placeholder="Ana"
        />
        <TextField
          label={strings.profile.contactPhone}
          value={form.contactPhone}
          onChangeText={(contactPhone) => update({ contactPhone })}
          keyboardType="phone-pad"
          placeholder="+381601234567"
        />
      </Card>

      <Button
        big
        label={saved ? strings.profile.saved : strings.profile.save}
        icon={saved ? 'check-circle' : 'content-save'}
        loading={saving}
        onPress={() => void save()}
      />
      <Button label={strings.profile.logout} icon="logout" variant="danger" loading={leaving} onPress={() => void logout()} />
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  flex: { flex: 1 },
  avatarRow: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.secondary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
});
