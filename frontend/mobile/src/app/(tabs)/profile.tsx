import { useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Keyboard, StyleSheet, View, type TextInputInstance } from 'react-native';

import { api } from '@/api/client';
import type { User } from '@/api/types';
import { Banner, Button, Card, Screen, ScreenHeader, SectionLabel, TextField, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { errorText, formatDate } from '@/lib/format';
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
        .me(settingsStore.get().serverAddress)
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

type Form = { name: string; contactName: string; contactPhone: string };

const fromUser = (user: User): Form => ({
  name: user.display_name,
  contactName: user.emergency_contact?.name ?? '',
  contactPhone: user.emergency_contact?.phone ?? '',
});

const initialsOf = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || '?';

function ProfileForm({ user }: { user: User }) {
  const [form, setForm] = useState<Form>(() => fromUser(user));
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [leaving, setLeaving] = useState(false);
  const contactNameRef = useRef<TextInputInstance>(null);
  const contactPhoneRef = useRef<TextInputInstance>(null);

  const stored = fromUser(user);
  const dirty =
    form.name.trim() !== stored.name ||
    form.contactName.trim() !== stored.contactName ||
    form.contactPhone.trim() !== stored.contactPhone;

  const update = (patch: Partial<Form>) => {
    setForm((f) => ({ ...f, ...patch }));
    setJustSaved(false);
  };

  async function save() {
    if (!dirty || saving) return;
    Keyboard.dismiss();
    setSaving(true);
    setError(null);
    const phone = form.contactPhone.trim();
    try {
      const next = await api.updateMe(settingsStore.get().serverAddress, {
        display_name: form.name.trim() || user.username,
        emergency_contact: phone ? { name: form.contactName.trim() || strings.profile.contactFallback, phone } : null,
      });
      setUser(next);
      setForm(fromUser(next)); // show exactly what the server stored (an empty name falls back to the username)
      setJustSaved(true);
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
    if (token) await api.logout(settingsStore.get().serverAddress).catch(() => {});
    liveStore.set({ summary: null }); // the next driver on this phone shouldn't see my last trip
    signedOut(); // the root layout's guard shows the login screen
  }

  return (
    <View style={styles.stack}>
      <Card style={styles.identity}>
        <View style={styles.avatar}>
          <Txt size="xl">{initialsOf(user.display_name)}</Txt>
        </View>
        <View style={styles.flex}>
          <Txt size="lg" weight="800">
            {user.display_name}
          </Txt>
          <Txt size="sm" tone="muted">
            @{user.username}
          </Txt>
          <Txt size="xs" tone="subtle">
            {strings.profile.memberSince(formatDate(user.created_at))}
          </Txt>
        </View>
      </Card>

      {error ? <Banner icon="alert-circle-outline" text={error} color={colors.destructive} /> : null}

      <SectionLabel>{strings.profile.details}</SectionLabel>
      <Card>
        <TextField
          label={strings.profile.name}
          placeholder={strings.profile.namePlaceholder}
          value={form.name}
          onChangeText={(name) => update({ name })}
          autoCapitalize="words"
          autoComplete="name"
          returnKeyType="next"
          submitBehavior="submit"
          onSubmitEditing={() => contactNameRef.current?.focus()}
        />
      </Card>

      <SectionLabel>{strings.profile.contact}</SectionLabel>
      <Card>
        <Txt size="sm" tone="muted">
          {strings.profile.contactHint}
        </Txt>
        <TextField
          ref={contactNameRef}
          label={strings.profile.contactName}
          placeholder={strings.profile.contactNamePlaceholder}
          value={form.contactName}
          onChangeText={(contactName) => update({ contactName })}
          autoCapitalize="words"
          returnKeyType="next"
          submitBehavior="submit"
          onSubmitEditing={() => contactPhoneRef.current?.focus()}
        />
        <TextField
          ref={contactPhoneRef}
          label={strings.profile.contactPhone}
          placeholder={strings.profile.contactPhonePlaceholder}
          value={form.contactPhone}
          onChangeText={(contactPhone) => update({ contactPhone })}
          keyboardType="phone-pad"
          autoComplete="tel"
          returnKeyType="done"
          onSubmitEditing={() => void save()}
        />
      </Card>

      <Button
        label={justSaved && !dirty ? strings.profile.saved : strings.profile.save}
        icon={justSaved && !dirty ? 'check-circle' : 'content-save'}
        loading={saving}
        disabled={!dirty}
        onPress={() => void save()}
      />

      <SectionLabel>{strings.profile.account}</SectionLabel>
      <Button label={strings.profile.logout} icon="logout" variant="danger" loading={leaving} onPress={() => void logout()} />
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  flex: { flex: 1 },
  identity: { flexDirection: 'row', alignItems: 'center', gap: 16 },
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
