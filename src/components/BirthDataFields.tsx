import React from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import DateTimeField from './DateTimeField';
import PlaceAutocomplete from './PlaceAutocomplete';
import { BirthData } from '../types/kundali';
import { colors, radius, spacing, typography } from '../theme/theme';

interface Props {
  value: BirthData;
  onChange: (data: BirthData) => void;
  // Skips the Naam field entirely — for the post-signup onboarding screen,
  // where the account holder already typed their name once on the signup
  // form (see useUserStore.hydrateAccountName) and re-asking read as a
  // broken/redundant flow. ProfileScreen (editing later) and GunaMilanScreen
  // (a second person's details, for compatibility matching) both leave this
  // unset since a name genuinely needs asking there.
  hideNameField?: boolean;
}

// No birth is in the future, and nobody using this app was born before 1900
// — a sane range beats letting the picker scroll through centuries.
const MIN_BIRTH_DATE = new Date(1900, 0, 1);
const MAX_BIRTH_DATE = new Date();

export default function BirthDataFields({ value, onChange, hideNameField }: Props) {
  const { t } = useTranslation();

  return (
    <View>
      {!hideNameField && (
        <Field
          label={t('profile.nameLabel')}
          value={value.name}
          onChangeText={(v) => onChange({ ...value, name: v })}
        />
      )}

      <View style={styles.field}>
        <DateTimeField
          label={t('profile.dateOfBirthLabel')}
          mode="date"
          value={value.dateOfBirth}
          onChange={(v) => onChange({ ...value, dateOfBirth: v })}
          placeholder="1990-01-25"
          minimumDate={MIN_BIRTH_DATE}
          maximumDate={MAX_BIRTH_DATE}
        />
      </View>

      <View style={styles.field}>
        <DateTimeField
          label={t('profile.timeOfBirthLabel')}
          mode="time"
          value={value.timeOfBirth}
          onChange={(v) => onChange({ ...value, timeOfBirth: v })}
          placeholder="06:42"
        />
      </View>

      <View style={styles.field}>
        <Text style={styles.fieldLabel}>{t('profile.placeOfBirthLabel')}</Text>
        <PlaceAutocomplete
          value={value.placeOfBirth}
          placeholder="Pune, Maharashtra, India"
          onChangeText={(text) =>
            // Editing the text after a selection invalidates that
            // selection's coordinates — better to fall back to the offline
            // table (see api/client.ts) than ship a stale lat/long that no
            // longer matches what's actually typed.
            onChange({ ...value, placeOfBirth: text, latitude: undefined, longitude: undefined, timezoneOffsetHours: undefined })
          }
          onSelect={(result) =>
            onChange({
              ...value,
              placeOfBirth: result.displayName,
              latitude: result.latitude,
              longitude: result.longitude,
              timezoneOffsetHours: result.timezoneOffsetHours,
            })
          }
        />
      </View>
    </View>
  );
}

function Field({
  label,
  value,
  onChangeText,
  placeholder,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        style={styles.input}
        placeholderTextColor={colors.textSecondary}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  field: {
    marginBottom: spacing.md,
  },
  fieldLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  input: {
    ...typography.body,
    color: colors.textPrimary,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    minHeight: 48,
    backgroundColor: colors.background,
  },
});
