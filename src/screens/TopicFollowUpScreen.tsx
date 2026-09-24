import { useNavigation, useRoute } from '@react-navigation/native';
import React, { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { submitOnboardingContext } from '../api/client';
import CosmicBackground from '../components/CosmicBackground';
import GlassSurface from '../components/GlassSurface';
import KeyboardAvoidingWrapper from '../components/KeyboardAvoidingWrapper';
import PrimaryButton from '../components/PrimaryButton';
import { ONBOARDING_TOPICS, OnboardingTopic, TOPIC_SLUG } from '../data/onboardingTopics';
import { useUserStore } from '../store/useUserStore';
import { colors, radius, spacing, typography } from '../theme/theme';
import { showAlert } from '../utils/crossPlatformAlert';

/** Product spec §2 — 2-4 high-value questions for whichever topic was
 * picked, ONE AT A TIME (never a form dumping every question at once, per
 * §8), submitted together at the end. A skipped/empty answer just moves on
 * — nothing here is required, since the whole point is staying quick. */
export default function TopicFollowUpScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const language = useUserStore((s) => s.language);
  const topicKey: OnboardingTopic = route.params?.topic ?? 'other';
  const topic = ONBOARDING_TOPICS.find((tp) => tp.key === topicKey) ?? ONBOARDING_TOPICS[ONBOARDING_TOPICS.length - 1];

  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState('');
  const [answers, setAnswers] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const isLast = index === topic.questionKeys.length - 1;

  const finish = async (allAnswers: string[]) => {
    setSubmitting(true);
    try {
      const qaPairs = topic.questionKeys
        .map((qKey, i) => ({ question: t(qKey) as string, answer: allAnswers[i]?.trim() ?? '' }))
        .filter((qa) => qa.answer.length > 0);
      if (qaPairs.length > 0) {
        await submitOnboardingContext(TOPIC_SLUG[topic.key], qaPairs, language);
      }
    } catch (err: any) {
      // Never blocks onboarding — personalization is a bonus, not a gate.
      showAlert(t('common.tryAgain'), err?.message ?? String(err));
    } finally {
      setSubmitting(false);
      navigation.navigate('AiProcessing');
    }
  };

  const handleNext = () => {
    const nextAnswers = [...answers, answer];
    setAnswer('');
    if (isLast) {
      finish(nextAnswers);
    } else {
      setAnswers(nextAnswers);
      setIndex(index + 1);
    }
  };

  return (
    <CosmicBackground style={styles.screen}>
      <KeyboardAvoidingWrapper>
      <View style={styles.content}>
        <View style={styles.progressRow}>
          {topic.questionKeys.map((_, i) => (
            <View key={i} style={[styles.dot, i <= index && styles.dotActive]} />
          ))}
        </View>

        <GlassSurface style={styles.questionCard}>
          <Text style={styles.question}>{t(topic.questionKeys[index])}</Text>
        </GlassSurface>

        <TextInput
          value={answer}
          onChangeText={setAnswer}
          placeholder={t('onboardingTopics.answerPlaceholder') as string}
          placeholderTextColor={colors.textSecondary}
          style={styles.input}
          multiline
          autoFocus
        />

        <View style={styles.actions}>
          <PrimaryButton
            label={isLast ? t('onboardingTopics.finish') : t('onboardingTopics.next')}
            onPress={handleNext}
            loading={submitting}
            disabled={submitting}
          />
          <Text onPress={handleNext} style={styles.skipText}>
            {t('onboardingTopics.skipQuestion')}
          </Text>
        </View>
      </View>
      </KeyboardAvoidingWrapper>
    </CosmicBackground>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: {
    flex: 1,
    padding: spacing.md,
    justifyContent: 'center',
    gap: spacing.lg,
  },
  progressRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.border,
  },
  dotActive: {
    backgroundColor: colors.primary,
  },
  questionCard: {
    padding: spacing.lg,
  },
  question: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
    textAlign: 'center',
  },
  input: {
    ...typography.body,
    color: colors.textPrimary,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    minHeight: 90,
    textAlignVertical: 'top',
    backgroundColor: colors.background,
  },
  actions: {
    gap: spacing.sm,
  },
  skipText: {
    ...typography.caption,
    color: colors.textSecondary,
    textAlign: 'center',
    textDecorationLine: 'underline',
  },
});
