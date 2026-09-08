import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import BulletList from '../components/BulletList';
import Card from '../components/Card';
import { HouseBreakdownList, YogaFindingsList } from '../components/ChartExplanation';
import ErrorState from '../components/ErrorState';
import LoadingState from '../components/LoadingState';
import PlanetPositionsTable from '../components/PlanetPositionsTable';
import PremiumLockNotice from '../components/PremiumLockNotice';
import SectionHeader from '../components/SectionHeader';
import SouthIndianChart from '../components/SouthIndianChart';
import { CHART_LABELS } from '../constants/astro';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useKundaliStore } from '../store/useKundaliStore';
import { useUserStore } from '../store/useUserStore';
import { ChartType } from '../types/kundali';
import { colors, radius, spacing, typography } from '../theme/theme';

const CHART_TYPES: ChartType[] = ['D1', 'D9', 'D10'];
const PREMIUM_CHARTS: ChartType[] = ['D9', 'D10'];

export default function ChartsScreen() {
  const { t } = useTranslation();
  const language = toContentLanguage(useUserStore((s) => s.language));
  const isPremium = useUserStore((s) => s.isPremium);
  const [selected, setSelected] = useState<ChartType>('D1');

  const chart = useKundaliStore((s) => s.charts[selected]?.[language]);
  const loading = useKundaliStore((s) => s.chartLoading);
  const error = useKundaliStore((s) => s.chartError);
  const fetchChart = useKundaliStore((s) => s.fetchChart);

  const isLocked = PREMIUM_CHARTS.includes(selected) && !isPremium;

  useEffect(() => {
    if (!isLocked) fetchChart(selected, language);
  }, [selected, language, isLocked]);

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.tabs}>
        {CHART_TYPES.map((type) => {
          const active = type === selected;
          return (
            <Pressable
              key={type}
              onPress={() => setSelected(type)}
              accessibilityRole="button"
              accessibilityLabel={CHART_LABELS[language][type]}
              accessibilityState={{ selected: active }}
              style={[styles.tab, active && styles.tabActive]}
            >
              <Text style={[styles.tabText, active && styles.tabTextActive]}>{type}</Text>
            </Pressable>
          );
        })}
      </View>

      <Text style={styles.chartTitle}>{CHART_LABELS[language][selected]}</Text>

      {isLocked && (
        <PremiumLockNotice message={t('charts.lockedMessage')} unlockLabel={t('charts.unlockButton')} />
      )}

      {!isLocked && loading && <LoadingState message={t('common.loading')} />}

      {!isLocked && !loading && error && (
        <ErrorState
          title={t('kundali.errorTitle')}
          message={t('kundali.errorMessage')}
          onRetry={() => fetchChart(selected, language)}
        />
      )}

      {!isLocked && !loading && !error && chart && (
        <>
          <Card style={styles.chartCard}>
            <View style={styles.chartWrap}>
              <SouthIndianChart chart={chart} language={language} size={300} />
            </View>
          </Card>

          <Card>
            <SectionHeader
              title={CHART_LABELS[language][selected]}
              voiceText={`${chart.summary} ${chart.keyPoints.join(' ')}`}
              voiceLabel={t('charts.listenToThisChart')}
              analyticsSource="kundali"
            />
            <Text style={styles.summary}>{chart.summary}</Text>
            <Text style={styles.keyPointsLabel}>{t('charts.keyPointsLabel')}</Text>
            <BulletList items={chart.keyPoints} />
          </Card>

          <Card>
            <SectionHeader title={t('kundali.planetaryPositionsTitle')} />
            <PlanetPositionsTable chart={chart} language={language} />
          </Card>

          {selected === 'D1' && (
            <Card>
              <SectionHeader title={t('charts.yogasTitle')} />
              <Text style={styles.yogasSubtitle}>{t('charts.yogasSubtitle')}</Text>
              <YogaFindingsList chart={chart} language={language} />
            </Card>
          )}

          <Card>
            <SectionHeader title={t('charts.houseByHouseTitle')} />
            <Text style={styles.yogasSubtitle}>{t('charts.houseByHouseSubtitle')}</Text>
            <HouseBreakdownList chart={chart} language={language} />
          </Card>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  tabs: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    padding: spacing.xs,
    marginBottom: spacing.md,
  },
  tab: {
    flex: 1,
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
  },
  tabActive: {
    backgroundColor: colors.primary,
  },
  tabText: {
    ...typography.bodyBold,
    color: colors.textSecondary,
  },
  tabTextActive: {
    color: colors.textInverse,
  },
  chartTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  chartCard: {
    alignItems: 'center',
  },
  chartWrap: {
    paddingVertical: spacing.sm,
  },
  summary: {
    ...typography.body,
    color: colors.textPrimary,
  },
  keyPointsLabel: {
    ...typography.bodyBold,
    color: colors.textSecondary,
    marginTop: spacing.md,
  },
  yogasSubtitle: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
});
