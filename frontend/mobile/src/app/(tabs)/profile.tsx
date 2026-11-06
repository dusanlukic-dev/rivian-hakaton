import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Button, Card, Screen, ScreenHeader, SectionLabel, TextField, Txt } from '@/components/ui';
import { strings } from '@/config/strings';
import { profileStore, slugify, useProfile, type Profile } from '@/state/profile';
import { colors } from '@/theme/colors';

export default function ProfileScreen() {
  const ready = useProfile((p) => p.ready);
  return (
    <Screen>
      <ScreenHeader title={strings.profile.title} subtitle={strings.profile.subtitle} />
      {/* mount the form only after AsyncStorage loaded, so it starts from the saved values */}
      {ready ? <ProfileForm initial={profileStore.get()} /> : null}
    </Screen>
  );
}

function ProfileForm({ initial }: { initial: Profile }) {
  const [form, setForm] = useState<Profile>({
    name: initial.name,
    driverId: initial.driverId,
    contactName: initial.contactName,
    contactPhone: initial.contactPhone,
  });
  const [saved, setSaved] = useState(false);
  const update = (patch: Partial<Profile>) => {
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

  function save() {
    profileStore.set({ ...form, driverId: form.driverId.trim() || slugify(form.name) });
    setSaved(true);
  }

  return (
    <View style={styles.stack}>
      <View style={styles.avatarRow}>
        <View style={styles.avatar}>
          <Txt size="xl">{initials}</Txt>
        </View>
        <View style={styles.flex}>
          <Txt size="lg" weight="800">
            {form.name || strings.profile.name}
          </Txt>
          <Txt size="sm" tone="muted">
            {form.driverId || slugify(form.name) || strings.profile.driverId}
          </Txt>
        </View>
      </View>

      <Card>
        <TextField
          label={strings.profile.name}
          value={form.name}
          onChangeText={(name) => update({ name })}
          autoCapitalize="words"
          placeholder="Matija Radović"
        />
        <TextField
          label={strings.profile.driverId}
          hint={strings.profile.driverIdHint}
          value={form.driverId}
          onChangeText={(driverId) => update({ driverId })}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder={slugify(form.name) || 'driver-1'}
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
        onPress={save}
        disabled={!form.name.trim() && !form.driverId.trim()}
      />
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
