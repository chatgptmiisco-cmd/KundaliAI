import React from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { BirthData } from '../types/kundali';
import { colors, radius, spacing, typography } from '../theme/theme';

interface Props {
  value: BirthData;
  onChange: (data: BirthData) => void;
}

export default function BirthDataFields({ value, onChange }: Props) {
  const { t } = useTranslation();

  return (
    <View>
      <Field
        label={t('profile.nameLabel')}
        value={value.name}
        onChangeText={(v) => onChange({ ...value, name: v })}
      />
      <Field
        label={t('profile.dateOfBirthLabel')}
        value={value.dateOfBirth}
        onChangeText={(v) => onChange({ ...value, dateOfBirth: v })}
        placeholder="1990-01-25"
      />
      <Field
        label={t('profile.timeOfBirthLabel')}
        value={value.timeOfBirth}
        onChangeText={(v) => onChange({ ...value, timeOfBirth: v })}
        placeholder="06:42"
      />
      <Field
        label={t('profile.placeOfBirthLabel')}
        value={value.placeOfBirth}
        onChangeText={(v) => onChange({ ...value, placeOfBirth: v })}
        placeholder="Pune, Maharashtra, India"
      />
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
