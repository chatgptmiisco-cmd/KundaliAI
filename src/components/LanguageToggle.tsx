import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '../store/useUserStore';
import { AppLanguage } from '../types/kundali';
import { colors, minTouchTarget, radius, spacing, typography } from '../theme/theme';

const OPTIONS: { value: AppLanguage; label: string }[] = [
  { value: 'en', label: 'EN' },
  { value: 'hinglish', label: 'Hinglish' },
  { value: 'hi', label: 'हिं' },
];

export default function LanguageToggle({ inverse }: { inverse?: boolean }) {
  const { i18n } = useTranslation();
  const language = useUserStore((s) => s.language);
  const setLanguage = useUserStore((s) => s.setLanguage);

  const select = (value: AppLanguage) => {
    setLanguage(value);
    i18n.changeLanguage(value);
  };

  return (
    <View style={[styles.wrap, inverse && styles.wrapInverse]}>
      {OPTIONS.map((opt) => {
        const active = opt.value === language;
        return (
          <Pressable
            key={opt.value}
            onPress={() => select(opt.value)}
            accessibilityRole="button"
            accessibilityLabel={opt.label}
            accessibilityState={{ selected: active }}
            style={[
              styles.pill,
              active && (inverse ? styles.pillActiveInverse : styles.pillActive),
            ]}
          >
            <Text
              style={[
                styles.label,
                inverse && styles.labelInverse,
                active && (inverse ? styles.labelActiveInverse : styles.labelActive),
              ]}
            >
              {opt.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.primary,
    padding: 2,
    gap: 2,
  },
  wrapInverse: {
    borderColor: 'rgba(255,255,255,0.6)',
  },
  pill: {
    minHeight: minTouchTarget - 4,
    minWidth: 40,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pillActive: {
    backgroundColor: colors.primary,
  },
  pillActiveInverse: {
    backgroundColor: 'rgba(255,255,255,0.25)',
  },
  label: {
    ...typography.caption,
    fontSize: 13,
    color: colors.primary,
  },
  labelInverse: {
    color: colors.textInverse,
  },
  labelActive: {
    color: colors.textInverse,
  },
  labelActiveInverse: {
    color: colors.textInverse,
  },
});
