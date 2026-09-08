import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import React, { useMemo, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import Card from '../components/Card';
import ErrorState from '../components/ErrorState';
import LoadingState from '../components/LoadingState';
import PrimaryButton from '../components/PrimaryButton';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useKundaliStore } from '../store/useKundaliStore';
import { useUserStore } from '../store/useUserStore';
import { colors, spacing, typography } from '../theme/theme';

const PASS_THRESHOLD = 75;

export default function ValidationScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const language = useUserStore((s) => s.language);
  const setAccuracyScore = useUserStore((s) => s.setAccuracyScore);
  const contentLanguage = toContentLanguage(language);

  const summary = useKundaliStore((s) => s.summary[contentLanguage]);
  const complete = useKundaliStore((s) => s.complete[contentLanguage]);
  const summaryError = useKundaliStore((s) => s.summaryError);
  const completeError = useKundaliStore((s) => s.completeError);
  const fetchSummary = useKundaliStore((s) => s.fetchSummary);
  const fetchComplete = useKundaliStore((s) => s.fetchComplete);

  const validationQuestions = useKundaliStore((s) => s.validationQuestions[contentLanguage]);
  const validationQuestionsError = useKundaliStore((s) => s.validationQuestionsError);
  const fetchValidationQuestions = useKundaliStore((s) => s.fetchValidationQuestions);

  // Real dasha-timeline questions ("did this actually happen to you") are the
  // real thing — they're genuinely different per person, tied to specific
  // past periods from this chart. A brand-new chart with too little elapsed
  // history to ask about falls back to the older personality-statement quiz.
  const statements = useMemo(() => {
    if (validationQuestions && validationQuestions.length >= 2) {
      return validationQuestions.map((q) => q.statement);
    }
    if (summary && complete) {
      const personality = complete.sections.find((s) => s.id === 'personalityNature');
      const health = complete.sections.find((s) => s.id === 'healthTemperament');
      return [
        summary.coreStrength,
        summary.coreChallenge,
        personality?.summary,
        health?.summary,
      ].filter((x): x is string => !!x);
    }
    return [];
  }, [validationQuestions, summary, complete]);

  const [step, setStep] = useState(0);
  const [yesCount, setYesCount] = useState(0);
  const [finished, setFinished] = useState(false);

  if (statements.length === 0) {
    if (summaryError || completeError || validationQuestionsError) {
      return (
        <ErrorState
          title={t('kundali.errorTitle')}
          message={t('kundali.errorMessage')}
          onRetry={() => {
            fetchSummary(contentLanguage);
            fetchComplete(contentLanguage);
            fetchValidationQuestions(contentLanguage);
          }}
        />
      );
    }
    return <LoadingState message={t('common.loading')} />;
  }

  const handleAnswer = (isYes: boolean) => {
    const nextYesCount = isYes ? yesCount + 1 : yesCount;
    setYesCount(nextYesCount);
    if (step + 1 < statements.length) {
      setStep(step + 1);
    } else {
      const percent = Math.round((nextYesCount / statements.length) * 100);
      setAccuracyScore(percent);
      setFinished(true);
    }
  };

  if (!finished) {
    return (
      <View style={styles.content}>
        <Text style={styles.subtitle}>{t('validation.subtitle')}</Text>
        <Text style={styles.progress}>
          {step + 1} / {statements.length}
        </Text>

        <Card style={styles.statementCard}>
          <Text style={styles.statementText}>{statements[step]}</Text>
        </Card>

        <View style={styles.answerRow}>
          <PrimaryButton label={t('validation.yes')} onPress={() => handleAnswer(true)} />
          <PrimaryButton
            label={t('validation.no')}
            variant="outline"
            onPress={() => handleAnswer(false)}
          />
        </View>
      </View>
    );
  }

  const percent = Math.round((yesCount / statements.length) * 100);
  const passed = percent >= PASS_THRESHOLD;

  return (
    <View style={styles.content}>
      <Card style={styles.resultCard}>
        <Ionicons
          name={passed ? 'checkmark-circle' : 'information-circle'}
          size={40}
          color={passed ? colors.success : colors.premium}
        />
        <Text style={styles.resultPercent}>{percent}%</Text>
        <Text style={styles.resultTitle}>
          {passed ? t('validation.resultTitleHigh') : t('validation.resultTitleLow')}
        </Text>
        <Text style={styles.resultMessage}>
          {passed
            ? t('validation.resultHighMessage', { percent })
            : t('validation.resultLowMessage', { percent })}
        </Text>
      </Card>

      {passed ? (
        <PrimaryButton
          label={t('validation.continueButton')}
          onPress={() => navigation.replace('Preferences')}
        />
      ) : (
        <View style={styles.answerRow}>
          <PrimaryButton
            label={t('validation.continueAnyway')}
            onPress={() => navigation.replace('Preferences')}
          />
          <PrimaryButton
            label={t('validation.editBirthDetails')}
            variant="outline"
            onPress={() => navigation.navigate('BirthData')}
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  content: {
    flex: 1,
    padding: spacing.md,
    backgroundColor: colors.background,
  },
  subtitle: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  progress: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.md,
  },
  statementCard: {
    minHeight: 140,
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  statementText: {
    ...typography.title,
    color: colors.textPrimary,
  },
  answerRow: {
    gap: spacing.sm,
  },
  resultCard: {
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.lg,
  },
  resultPercent: {
    ...typography.display,
    color: colors.primary,
  },
  resultTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
  },
  resultMessage: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
    marginTop: spacing.xs,
  },
});
