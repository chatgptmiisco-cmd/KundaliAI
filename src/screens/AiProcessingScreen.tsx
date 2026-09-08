import { useNavigation } from '@react-navigation/native';
import { LinearGradient } from 'expo-linear-gradient';
import React, { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import PlanetLoader from '../components/PlanetLoader';
import StarField from '../components/StarField';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useKundaliStore } from '../store/useKundaliStore';
import { useUserStore } from '../store/useUserStore';
import { colors, fontFamily, radius, spacing, typography } from '../theme/theme';

const TOTAL_MS = 10000;

export default function AiProcessingScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const language = useUserStore((s) => s.language);
  const fetchSummary = useKundaliStore((s) => s.fetchSummary);
  const fetchComplete = useKundaliStore((s) => s.fetchComplete);
  const fetchManglik = useKundaliStore((s) => s.fetchManglik);
  const fetchValidationQuestions = useKundaliStore((s) => s.fetchValidationQuestions);

  const steps = t('onboarding.processingMessages', { returnObjects: true }) as string[];
  const stepMs = TOTAL_MS / steps.length;
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    const contentLanguage = toContentLanguage(language);
    fetchSummary(contentLanguage);
    fetchComplete(contentLanguage);
    fetchManglik(contentLanguage);
    fetchValidationQuestions(contentLanguage);

    const stepTimer = setInterval(() => {
      setStepIndex((i) => Math.min(steps.length - 1, i + 1));
    }, stepMs);

    const doneTimer = setTimeout(() => {
      navigation.replace('Validation');
    }, TOTAL_MS);

    return () => {
      clearInterval(stepTimer);
      clearTimeout(doneTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <LinearGradient
      colors={['#241d3d', colors.primaryDark, colors.primary]}
      start={{ x: 0.1, y: 0 }}
      end={{ x: 0.9, y: 1 }}
      style={styles.wrap}
    >
      <StarField />
      <PlanetLoader size={140} dark />
      <Text style={styles.title}>{t('onboarding.aiProcessingTitle')}</Text>

      <View style={styles.steps}>
        {steps.map((step, idx) => {
          const isDone = idx < stepIndex;
          const isActive = idx === stepIndex;
          return (
            <View key={step} style={[styles.step, isActive && styles.stepActive]}>
              <Text style={[styles.stepMark, isDone && styles.stepMarkDone]}>
                {isDone ? '✓' : idx + 1}
              </Text>
              <Text style={[styles.stepText, (isActive || isDone) && styles.stepTextLit]}>{step}</Text>
            </View>
          );
        })}
      </View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  title: {
    ...typography.title,
    color: colors.textInverse,
    marginTop: spacing.lg,
    marginBottom: spacing.xl,
    textAlign: 'center',
  },
  steps: {
    width: '100%',
    gap: spacing.xs,
  },
  step: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  stepActive: {
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderColor: 'rgba(255,255,255,0.14)',
  },
  stepMark: {
    ...typography.caption,
    width: 20,
    textAlign: 'center',
    color: 'rgba(255,255,255,0.35)',
    fontFamily: fontFamily.bold,
  },
  stepMarkDone: {
    color: '#85c7ad',
  },
  stepText: {
    ...typography.caption,
    color: 'rgba(255,255,255,0.35)',
    flexShrink: 1,
  },
  stepTextLit: {
    color: colors.textInverse,
  },
});
