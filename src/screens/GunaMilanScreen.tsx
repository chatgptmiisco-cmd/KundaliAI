import React, { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { getGunaMilan } from '../api/client';
import BirthDataFields from '../components/BirthDataFields';
import Card from '../components/Card';
import ErrorState from '../components/ErrorState';
import LoadingState from '../components/LoadingState';
import PrimaryButton from '../components/PrimaryButton';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useUserStore } from '../store/useUserStore';
import { BirthData, GunaMilanResult } from '../types/kundali';
import { colors, radius, spacing, typography } from '../theme/theme';

const emptyPartner: BirthData = { name: '', dateOfBirth: '', timeOfBirth: '', placeOfBirth: '' };

const VERDICT_COLOR: Record<GunaMilanResult['verdict'], string> = {
  excellent: colors.success,
  good: colors.success,
  average: colors.accent,
  not_recommended: colors.premium,
};

export default function GunaMilanScreen() {
  const { t } = useTranslation();
  const language = toContentLanguage(useUserStore((s) => s.language));

  const [partner, setPartner] = useState<BirthData>(emptyPartner);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [result, setResult] = useState<GunaMilanResult | null>(null);

  const canSubmit =
    partner.name.trim() && partner.dateOfBirth.trim() && partner.timeOfBirth.trim() && partner.placeOfBirth.trim();

  const handleMatch = async () => {
    setLoading(true);
    setError(false);
    try {
      const data = await getGunaMilan(partner, language);
      setResult(data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <LoadingState message={t('gunaMilan.matching')} />;
  }

  if (error) {
    return <ErrorState title={t('kundali.errorTitle')} message={t('kundali.errorMessage')} onRetry={handleMatch} />;
  }

  if (result) {
    return (
      <ScrollView contentContainerStyle={styles.content}>
        <Card style={styles.scoreCard}>
          <Text style={styles.scoreValue}>
            {result.totalScore} / {result.maxTotal}
          </Text>
          <View style={[styles.verdictPill, { backgroundColor: VERDICT_COLOR[result.verdict] }]}>
            <Text style={styles.verdictPillText}>{t(`gunaMilan.verdict.${result.verdict}`)}</Text>
          </View>
          <Text style={styles.verdictMessage}>{result.verdictMessage}</Text>
        </Card>

        <Card>
          <Text style={styles.moonRow}>
            {t('gunaMilan.yourMoon', { sign: result.yourMoonSign, nakshatra: result.yourNakshatra })}
          </Text>
          <Text style={styles.moonRow}>
            {t('gunaMilan.partnerMoon', { sign: result.partnerMoonSign, nakshatra: result.partnerNakshatra })}
          </Text>
        </Card>

        {result.mangalDoshaMismatch && result.mangalDoshaNote && (
          <Card style={styles.mangalCard}>
            <Text style={styles.mangalText}>{result.mangalDoshaNote}</Text>
          </Card>
        )}

        <Text style={styles.sectionTitle}>{t('gunaMilan.kootaBreakdown')}</Text>
        {result.kootas.map((k) => (
          <Card key={k.key} style={styles.kootaCard}>
            <View style={styles.kootaHeaderRow}>
              <Text style={styles.kootaLabel}>{k.label}</Text>
              <Text style={styles.kootaScore}>
                {k.score} / {k.maxScore}
              </Text>
            </View>
            <Text style={styles.kootaSummary}>{k.summary}</Text>
          </Card>
        ))}

        <PrimaryButton
          label={t('gunaMilan.matchAnother')}
          variant="outline"
          onPress={() => setResult(null)}
        />
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.subtitle}>{t('gunaMilan.formSubtitle')}</Text>
      <Card>
        <BirthDataFields value={partner} onChange={setPartner} />
      </Card>
      <PrimaryButton label={t('gunaMilan.matchButton')} onPress={handleMatch} disabled={!canSubmit} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
    gap: spacing.md,
  },
  subtitle: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  scoreCard: {
    alignItems: 'center',
    gap: spacing.xs,
  },
  scoreValue: {
    ...typography.display,
    color: colors.primary,
  },
  verdictPill: {
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    marginTop: spacing.xs,
  },
  verdictPillText: {
    ...typography.bodyBold,
    color: colors.textInverse,
  },
  verdictMessage: {
    ...typography.body,
    color: colors.textPrimary,
    textAlign: 'center',
    marginTop: spacing.sm,
  },
  moonRow: {
    ...typography.body,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  mangalCard: {
    backgroundColor: colors.premiumLight,
  },
  mangalText: {
    ...typography.body,
    color: colors.premium,
  },
  sectionTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
    marginTop: spacing.sm,
  },
  kootaCard: {
    gap: spacing.xs,
  },
  kootaHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  kootaLabel: {
    ...typography.bodyBold,
    color: colors.textPrimary,
    flex: 1,
    marginRight: spacing.sm,
  },
  kootaScore: {
    ...typography.bodyBold,
    color: colors.primary,
  },
  kootaSummary: {
    ...typography.caption,
    color: colors.textSecondary,
  },
});
