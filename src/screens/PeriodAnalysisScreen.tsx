import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { getCurrentDasha, getPeriodAnalysis } from '../api/client';
import BulletList from '../components/BulletList';
import Card from '../components/Card';
import ErrorState from '../components/ErrorState';
import LoadingState from '../components/LoadingState';
import PremiumLockNotice from '../components/PremiumLockNotice';
import SpeakerButton from '../components/SpeakerButton';
import { PLANET_NAMES } from '../constants/astro';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useKundaliStore } from '../store/useKundaliStore';
import { useUserStore } from '../store/useUserStore';
import { CurrentDasha, PeriodAnalysis } from '../types/kundali';
import { colors, fontFamily, radius, spacing, typography } from '../theme/theme';

export default function PeriodAnalysisScreen() {
  const { t } = useTranslation();
  const language = toContentLanguage(useUserStore((s) => s.language));
  const isPremium = useUserStore((s) => s.isPremium);
  const birthData = useUserStore((s) => s.birthData);

  const periods = useKundaliStore((s) => s.dasha[language]);
  const loading = useKundaliStore((s) => s.dashaLoading);
  const error = useKundaliStore((s) => s.dashaError);
  const fetchDasha = useKundaliStore((s) => s.fetchDasha);

  const [expanded, setExpanded] = useState<string | null>(null);
  // Real per-period analysis, fetched lazily as each period is expanded
  // (not baked into the timeline fetch — every period's rating/theme/risks
  // are a genuine calculation off that exact date range, not a per-lord
  // canned lookup).
  const [analyses, setAnalyses] = useState<Record<string, PeriodAnalysis>>({});
  const [analysisLoading, setAnalysisLoading] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // The precise three-level stack (Mahadasha > Antardasha > Pratyantardasha)
  // active today — the Pratyantardasha is the narrowest window the engine
  // computes and previously never reached this screen at all.
  const [currentDasha, setCurrentDasha] = useState<CurrentDasha | null>(null);

  useEffect(() => {
    fetchDasha(language, birthData.dateOfBirth);
    getCurrentDasha()
      .then(setCurrentDasha)
      .catch(() => setCurrentDasha(null));
  }, [language, birthData.dateOfBirth]);

  const loadAnalysis = (key: string, startDate: string, endDate: string) => {
    if (analyses[key]) return;
    setAnalysisLoading(key);
    setAnalysisError(null);
    getPeriodAnalysis(startDate, endDate, language)
      .then((data) => setAnalyses((prev) => ({ ...prev, [key]: data })))
      .catch(() => setAnalysisError(key))
      .finally(() => setAnalysisLoading((cur) => (cur === key ? null : cur)));
  };

  if (loading) {
    return <LoadingState message={t('common.loading')} />;
  }

  if (error || !periods) {
    return (
      <ErrorState
        title={t('kundali.errorTitle')}
        message={t('kundali.errorMessage')}
        onRetry={() => fetchDasha(language, birthData.dateOfBirth)}
      />
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.intro}>{t('periods.introText')}</Text>

      {currentDasha && (
        <Card style={styles.rightNowCard}>
          <Text style={styles.rightNowLabel}>{t('periods.rightNowLabel')}</Text>
          <Text style={styles.rightNowStack}>
            {PLANET_NAMES[language][currentDasha.mahadasha.planet]}
            {' › '}
            {PLANET_NAMES[language][currentDasha.antardasha.planet]}
            {' › '}
            {PLANET_NAMES[language][currentDasha.pratyantardasha.planet]}
          </Text>
          <Text style={styles.dateRange}>
            {currentDasha.pratyantardasha.startDate} – {currentDasha.pratyantardasha.endDate}
          </Text>
        </Card>
      )}

      {periods.map((period, idx) => {
        const key = `${period.planet}-${idx}`;
        const isOpen = expanded === key;
        const canViewDetails = isPremium || period.isCurrent;
        const analysis = analyses[key];

        return (
          <Card key={key}>
            <Pressable
              onPress={() => {
                const next = isOpen ? null : key;
                setExpanded(next);
                if (next && canViewDetails) loadAnalysis(key, period.startDate, period.endDate);
              }}
              accessibilityRole="button"
              accessibilityLabel={PLANET_NAMES[language][period.planet]}
              style={styles.headerRow}
            >
              <View style={styles.headerLeft}>
                <Text style={styles.planetName}>{PLANET_NAMES[language][period.planet]}</Text>
                <Text style={styles.dateRange}>
                  {period.startDate} – {period.endDate}
                </Text>
              </View>
              <View style={styles.headerRight}>
                {period.isCurrent && (
                  <View style={styles.currentPill}>
                    <Text style={styles.currentPillText}>{t('periods.currentBadge')}</Text>
                  </View>
                )}
                {!canViewDetails && (
                  <Ionicons name="lock-closed-outline" size={18} color={colors.premium} />
                )}
                <Ionicons
                  name={isOpen ? 'chevron-up' : 'chevron-down'}
                  size={22}
                  color={colors.textSecondary}
                />
              </View>
            </Pressable>

            {isOpen && !canViewDetails && (
              <View style={{ marginTop: spacing.md }}>
                <PremiumLockNotice
                  message={t('periods.lockedMessage')}
                  unlockLabel={t('periods.unlockButton')}
                />
              </View>
            )}

            {isOpen && canViewDetails && analysisLoading === key && (
              <View style={{ marginTop: spacing.md }}>
                <LoadingState message={t('common.loading')} />
              </View>
            )}

            {isOpen && canViewDetails && analysisError === key && (
              <View style={{ marginTop: spacing.md }}>
                <Text style={styles.summary}>{t('periods.analysisErrorMessage')}</Text>
              </View>
            )}

            {isOpen && canViewDetails && analysis && (
              <View style={styles.details}>
                <SpeakerButton
                  label={t('periods.listenToThisPeriod')}
                  title={PLANET_NAMES[language][period.planet]}
                  text={`${analysis.theme} ${analysis.summary}`}
                  analyticsSource="kundali"
                  compact
                />
                <View style={styles.ratingRow}>
                  <Text style={styles.ratingBadge}>{analysis.rating}/10</Text>
                  <Text style={styles.themeText}>{analysis.theme}</Text>
                </View>
                <Text style={styles.summary}>{analysis.summary}</Text>
                {analysis.remainingFreeAnalysesThisMonth !== null && (
                  <Text style={styles.quotaText}>
                    {t('periods.remainingFreeAnalyses', { count: analysis.remainingFreeAnalysesThisMonth })}
                  </Text>
                )}

                <Text style={styles.subLabel}>{t('periods.risksLabel')}</Text>
                <BulletList items={analysis.risks} />
                <Text style={styles.subLabel}>{t('periods.opportunitiesLabel')}</Text>
                <BulletList items={analysis.opportunities} />

                <Text style={styles.subLabel}>{t('periods.subPeriodsLabel')}</Text>
                <BulletList
                  items={period.subPeriods.map((sub) => {
                    const label = `${PLANET_NAMES[language][sub.planet]} (${sub.startDate} – ${sub.endDate})`;
                    return sub.isCurrent ? `${label} — ${t('periods.currentBadge')}` : label;
                  })}
                />
              </View>
            )}
          </Card>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  intro: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.md,
  },
  rightNowCard: {
    backgroundColor: colors.primaryLight,
    borderColor: colors.primary,
    borderWidth: 1,
  },
  rightNowLabel: {
    ...typography.caption,
    color: colors.primaryDark,
    fontFamily: fontFamily.bold,
    marginBottom: spacing.xs,
  },
  rightNowStack: {
    ...typography.bodyBold,
    color: colors.primaryDark,
  },
  quotaText: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: spacing.sm,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 48,
  },
  headerLeft: {
    flexShrink: 1,
  },
  planetName: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
  },
  dateRange: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: 2,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  currentPill: {
    backgroundColor: colors.successLight,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  currentPillText: {
    ...typography.caption,
    color: colors.success,
    fontFamily: fontFamily.bold,
  },
  ratingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  ratingBadge: {
    ...typography.bodyBold,
    color: colors.primary,
  },
  themeText: {
    ...typography.body,
    color: colors.textPrimary,
    flexShrink: 1,
  },
  details: {
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  summary: {
    ...typography.body,
    color: colors.textPrimary,
    marginTop: spacing.sm,
  },
  subLabel: {
    ...typography.bodyBold,
    color: colors.textSecondary,
    marginTop: spacing.md,
  },
});
