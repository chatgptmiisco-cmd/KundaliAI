import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import PrimaryButton from '../components/PrimaryButton';
import { useUserStore } from '../store/useUserStore';
import { PreferenceKey } from '../types/kundali';
import { colors, radius, spacing, typography } from '../theme/theme';

const OPTIONS: { key: PreferenceKey; icon: keyof typeof Ionicons.glyphMap }[] = [
  { key: 'family', icon: 'people-outline' },
  { key: 'health', icon: 'fitness-outline' },
  { key: 'career', icon: 'briefcase-outline' },
  { key: 'marriageRelationships', icon: 'heart-outline' },
  { key: 'friends', icon: 'happy-outline' },
];

export default function PreferencesScreen() {
  const { t } = useTranslation();
  const setPreferences = useUserStore((s) => s.setPreferences);
  const finishOnboarding = useUserStore((s) => s.finishOnboarding);
  const [selected, setSelected] = useState<PreferenceKey[]>([]);

  const toggle = (key: PreferenceKey) => {
    setSelected((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  };

  const handleContinue = () => {
    setPreferences(selected);
    finishOnboarding();
  };

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.subtitle}>{t('preferences.subtitle')}</Text>

      <View style={styles.grid}>
        {OPTIONS.map((opt) => {
          const active = selected.includes(opt.key);
          return (
            <Pressable
              key={opt.key}
              onPress={() => toggle(opt.key)}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              style={[styles.chip, active && styles.chipActive]}
            >
              <Ionicons
                name={opt.icon}
                size={22}
                color={active ? colors.textInverse : colors.primary}
              />
              <Text style={[styles.chipText, active && styles.chipTextActive]}>
                {t(`preferences.${opt.key}`)}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <View style={{ height: spacing.lg }} />
      {selected.length === 0 && (
        <Text style={styles.hint}>{t('preferences.selectAtLeastOne')}</Text>
      )}
      <PrimaryButton
        label={t('preferences.continueButton')}
        disabled={selected.length === 0}
        onPress={handleContinue}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  subtitle: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.lg,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    minHeight: 52,
  },
  chipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  chipText: {
    ...typography.bodyBold,
    color: colors.primary,
  },
  chipTextActive: {
    color: colors.textInverse,
  },
  hint: {
    ...typography.caption,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.sm,
  },
});
