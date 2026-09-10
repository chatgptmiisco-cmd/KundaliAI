import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import BulletList from '../components/BulletList';
import Card from '../components/Card';
import ErrorState from '../components/ErrorState';
import LoadingState from '../components/LoadingState';
import SectionHeader from '../components/SectionHeader';
import { PLANET_NAMES } from '../constants/astro';
import { toContentLanguage } from '../i18n/contentLanguage';
import { usePredictionStore } from '../store/usePredictionStore';
import { useUserStore } from '../store/useUserStore';
import { QuarterOutlook, YearOutlook } from '../types/kundali';
import { colors, fontFamily, radius, spacing, typography } from '../theme/theme';

type ViewMode = 'this' | 'next' | 'multi';

const CURRENT_YEAR = new Date().getFullYear();

export default function PredictionsScreen() {
  const { t } = useTranslation();
  const language = toContentLanguage(useUserStore((s) => s.language));

  const [viewMode, setViewMode] = useState<ViewMode>('this');

  const singleYear = viewMode === 'next' ? CURRENT_YEAR + 1 : CURRENT_YEAR;
  const yearOutlook = usePredictionStore((s) => s.yearOutlooks[singleYear]?.[language]);
  const yearLoading = usePredictionStore((s) => s.yearOutlookLoading);
  const yearError = usePredictionStore((s) => s.yearOutlookError);
  const fetchYearOutlook = usePredictionStore((s) => s.fetchYearOutlook);

  const multiYearOutlook = usePredictionStore((s) => s.multiYearOutlooks[2]?.[language]);
  const multiLoading = usePredictionStore((s) => s.multiYearOutlookLoading);
  const multiError = usePredictionStore((s) => s.multiYearOutlookError);
  const fetchMultiYearOutlook = usePredictionStore((s) => s.fetchMultiYearOutlook);

  const marriageTiming = usePredictionStore((s) => s.marriageTiming[language]);
  const marriageLoading = usePredictionStore((s) => s.marriageTimingLoading);
  const marriageError = usePredictionStore((s) => s.marriageTimingError);
  const fetchMarriageTiming = usePredictionStore((s) => s.fetchMarriageTiming);

  useEffect(() => {
    if (viewMode === 'multi') {
      fetchMultiYearOutlook(language, 2);
    } else {
      fetchYearOutlook(language, singleYear);
    }
  }, [viewMode, language, singleYear]);

  useEffect(() => {
    fetchMarriageTiming(language);
  }, [language]);

  const yearsToShow: YearOutlook[] | undefined =
    viewMode === 'multi' ? multiYearOutlook : yearOutlook ? [yearOutlook] : undefined;
  const yearsLoading = viewMode === 'multi' ? multiLoading : yearLoading;
  const yearsError = viewMode === 'multi' ? multiError : yearError;
  const retryYears = () =>
    viewMode === 'multi' ? fetchMultiYearOutlook(language, 2) : fetchYearOutlook(language, singleYear);

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.intro}>{t('predictions.introText')}</Text>

      <View style={styles.viewToggle}>
        {(['this', 'next', 'multi'] as ViewMode[]).map((mode) => (
          <Pressable
            key={mode}
            onPress={() => setViewMode(mode)}
            style={[styles.viewToggleButton, viewMode === mode && styles.viewToggleButtonActive]}
          >
            <Text style={[styles.viewToggleText, viewMode === mode && styles.viewToggleTextActive]}>
              {t(`predictions.viewMode.${mode}`)}
            </Text>
          </Pressable>
        ))}
      </View>

      {yearsLoading && <LoadingState message={t('common.loading')} />}
      {!yearsLoading && yearsError && (
        <ErrorState
          title={t('predictions.errorTitle')}
          message={t('predictions.errorMessage')}
          onRetry={retryYears}
        />
      )}
      {!yearsLoading &&
        !yearsError &&
        yearsToShow?.map((year) => <YearOutlookSection key={year.year} year={year} language={language} />)}

      <SectionHeader title={t('predictions.marriageTiming.sectionTitle')} />
      <Text style={styles.marriageIntro}>{t('predictions.marriageTiming.introText')}</Text>

      {marriageLoading && <LoadingState message={t('common.loading')} />}
      {!marriageLoading && marriageError && (
        <ErrorState
          title={t('predictions.errorTitle')}
          message={t('predictions.errorMessage')}
          onRetry={() => fetchMarriageTiming(language)}
        />
      )}
      {!marriageLoading && !marriageError && marriageTiming && (
        <>
          {marriageTiming.windows.length === 0 && (
            <Card>
              <Text style={styles.summary}>{t('predictions.marriageTiming.noWindowsFound')}</Text>
            </Card>
          )}
          {marriageTiming.windows.map((window, idx) => (
            <Card key={idx}>
              <View style={styles.windowHeaderRow}>
                <Text style={styles.dateRange}>
                  {window.startDate} – {window.endDate}
                </Text>
                {window.transitCorroborated && (
                  <View style={styles.corroboratedPill}>
                    <Text style={styles.corroboratedPillText}>
                      {t('predictions.marriageTiming.corroboratedBadge')}
                    </Text>
                  </View>
                )}
              </View>
              <Text style={styles.windowLords}>
                {PLANET_NAMES[language][window.mahadashaLord]} {'›'} {PLANET_NAMES[language][window.antardashaLord]}
              </Text>
              <Text style={styles.summary}>{window.reason}</Text>
            </Card>
          ))}
          {marriageTiming.manglikNote && (
            <Card style={styles.manglikCard}>
              <Text style={styles.summary}>{marriageTiming.manglikNote}</Text>
            </Card>
          )}
        </>
      )}
    </ScrollView>
  );
}

function YearOutlookSection({ year, language }: { year: YearOutlook; language: 'en' | 'hi' }) {
  const { t } = useTranslation();
  return (
    <>
      <Card style={styles.overallCard}>
        <Text style={styles.overallYearLabel}>{year.year}</Text>
        <View style={styles.ratingRow}>
          <Text style={styles.ratingBadge}>{year.overallRating}/10</Text>
          <Text style={styles.themeText}>{year.overallTheme}</Text>
        </View>
        <Text style={styles.varsheshwarText}>
          {t('predictions.varsheshwarLabel', { planet: PLANET_NAMES[language][year.varsheshwar] })}
        </Text>
      </Card>

      {year.quarters.map((quarter, idx) => (
        <QuarterCard key={idx} quarter={quarter} language={language} />
      ))}
    </>
  );
}

function QuarterCard({ quarter, language }: { quarter: QuarterOutlook; language: 'en' | 'hi' }) {
  const { t } = useTranslation();
  return (
    <Card>
      <View style={styles.headerRow}>
        <Text style={styles.dateRange}>
          {quarter.startDate} – {quarter.endDate}
        </Text>
        <Text style={styles.ratingBadge}>{quarter.rating}/10</Text>
      </View>
      <Text style={styles.summary}>{quarter.theme}</Text>
      {quarter.opportunities.length > 0 && (
        <>
          <Text style={styles.subLabel}>{t('predictions.opportunitiesLabel')}</Text>
          <BulletList items={quarter.opportunities} />
        </>
      )}
      {quarter.risks.length > 0 && (
        <>
          <Text style={styles.subLabel}>{t('predictions.risksLabel')}</Text>
          <BulletList items={quarter.risks} />
        </>
      )}
    </Card>
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
  viewToggle: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    padding: spacing.xs,
    marginBottom: spacing.md,
  },
  viewToggleButton: {
    flex: 1,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
  },
  viewToggleButtonActive: {
    backgroundColor: colors.primary,
  },
  viewToggleText: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  viewToggleTextActive: {
    color: colors.textInverse,
  },
  overallCard: {
    backgroundColor: colors.primaryLight,
    borderColor: colors.primary,
    borderWidth: 1,
  },
  overallYearLabel: {
    ...typography.caption,
    color: colors.primaryDark,
    fontFamily: fontFamily.bold,
    marginBottom: spacing.xs,
  },
  varsheshwarText: {
    ...typography.caption,
    color: colors.primaryDark,
    marginTop: spacing.sm,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  dateRange: {
    ...typography.caption,
    color: colors.textSecondary,
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
  marriageIntro: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  windowHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  windowLords: {
    ...typography.bodyBold,
    color: colors.textPrimary,
    marginTop: spacing.xs,
  },
  corroboratedPill: {
    backgroundColor: colors.successLight,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  corroboratedPillText: {
    ...typography.caption,
    color: colors.success,
    fontFamily: fontFamily.bold,
  },
  manglikCard: {
    backgroundColor: colors.surfaceMuted,
  },
});
