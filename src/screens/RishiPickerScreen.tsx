import { useNavigation } from '@react-navigation/native';
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { RISHIS } from '../constants/rishis';
import { colors, elevation, fontFamily, radius, spacing, typography } from '../theme/theme';

export default function RishiPickerScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.eyebrow}>{t('common.appName')}</Text>
      <Text style={styles.title}>{t('rishiPicker.screenTitle')}</Text>
      <Text style={styles.subtitle}>{t('rishiPicker.subtitle')}</Text>

      <View style={styles.grid}>
        {RISHIS.map((rishi) => (
          <Pressable
            key={rishi.id}
            onPress={() => navigation.navigate('RishiChat', { rishiId: rishi.id })}
            accessibilityRole="button"
            accessibilityLabel={rishi.name}
            style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
          >
            <View
              style={[
                styles.portrait,
                { backgroundColor: rishi.gradient[1], shadowColor: rishi.shade },
              ]}
            >
              <Text style={styles.portraitText}>{rishi.initial}</Text>
            </View>
            <Text style={styles.name}>{rishi.name}</Text>
            <Text style={styles.focus}>{t(`rishiPicker.${rishi.id}.focus`)}</Text>
            <Text style={styles.tag}>{t(`rishiPicker.${rishi.id}.tag`)}</Text>
            <Text style={styles.description}>{t(`rishiPicker.${rishi.id}.description`)}</Text>
            <View style={[styles.openPill, { backgroundColor: rishi.gradient[1] }]}>
              <Text style={styles.openPillText}>{t('rishiPicker.openButton')}</Text>
            </View>
          </Pressable>
        ))}
      </View>

      <Text style={styles.disclaimer}>{t('rishiPicker.disclaimer')}</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  eyebrow: {
    ...typography.caption,
    color: colors.accentDark,
    fontFamily: fontFamily.bold,
    letterSpacing: 1,
    textTransform: 'uppercase',
    marginBottom: spacing.xs,
  },
  title: {
    ...typography.display,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  subtitle: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.lg,
  },
  grid: {
    gap: spacing.md,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    alignItems: 'center',
    ...elevation.card,
  },
  cardPressed: {
    backgroundColor: colors.surfaceMuted,
  },
  portrait: {
    width: 72,
    height: 72,
    borderRadius: radius.xl,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 1,
    shadowRadius: 18,
    elevation: 6,
  },
  portraitText: {
    fontSize: 30,
    fontFamily: fontFamily.displayBold,
    color: colors.textInverse,
  },
  name: {
    ...typography.title,
    color: colors.textPrimary,
  },
  focus: {
    ...typography.bodyBold,
    color: colors.primary,
    marginTop: 2,
  },
  tag: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  description: {
    ...typography.caption,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.md,
  },
  openPill: {
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  openPillText: {
    ...typography.caption,
    color: colors.textInverse,
    fontFamily: fontFamily.bold,
  },
  disclaimer: {
    ...typography.caption,
    color: colors.textSecondary,
    textAlign: 'center',
    marginTop: spacing.lg,
  },
});
