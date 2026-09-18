import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text } from 'react-native';
import { useTranslation } from 'react-i18next';
import CosmicBackground from '../components/CosmicBackground';
import GlassSurface from '../components/GlassSurface';
import { ONBOARDING_TOPICS, OnboardingTopic } from '../data/onboardingTopics';
import { colors, radius, spacing, typography } from '../theme/theme';

/** Product spec §1 — the one question asked right after birth data, before
 * anything else: "What would you most like clarity about right now?" A
 * single tap here is all this screen asks for; the 2-4 follow-up questions
 * for whichever topic gets picked live on TopicFollowUpScreen next. */
export default function TopicSelectionScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();

  const handleSelect = (topic: OnboardingTopic) => {
    navigation.navigate('TopicFollowUp', { topic });
  };

  return (
    <CosmicBackground style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <GlassSurface style={styles.headerCard}>
          <Text style={styles.title}>{t('onboardingTopics.title')}</Text>
          <Text style={styles.subtitle}>{t('onboardingTopics.subtitle')}</Text>
        </GlassSurface>

        {ONBOARDING_TOPICS.map((topic) => (
          <Pressable
            key={topic.key}
            onPress={() => handleSelect(topic.key)}
            accessibilityRole="button"
            style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
          >
            <Ionicons name={topic.icon as any} size={22} color={colors.primary} />
            <Text style={styles.rowText}>{t(topic.labelKey)}</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.textSecondary} />
          </Pressable>
        ))}
      </ScrollView>
    </CosmicBackground>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
    gap: spacing.sm,
  },
  headerCard: {
    padding: spacing.md,
    marginBottom: spacing.xs,
  },
  title: {
    ...typography.title,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  subtitle: {
    ...typography.body,
    color: colors.textSecondary,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    minHeight: 56,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  rowPressed: {
    opacity: 0.85,
  },
  rowText: {
    ...typography.bodyBold,
    color: colors.textPrimary,
    flex: 1,
  },
});
