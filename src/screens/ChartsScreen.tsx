import { useNavigation } from '@react-navigation/native';
import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { getCurrentDasha, getDailyReading } from '../api/client';
import BulletList from '../components/BulletList';
import Card from '../components/Card';
import { HouseBreakdownList, YogaFindingsList } from '../components/ChartExplanation';
import ErrorState from '../components/ErrorState';
import IdentityBasics from '../components/IdentityBasics';
import LoadingState from '../components/LoadingState';
import PlanetPositionsTable from '../components/PlanetPositionsTable';
import PremiumLockNotice from '../components/PremiumLockNotice';
import PrimaryButton from '../components/PrimaryButton';
import PurusharthaBreakdown from '../components/PurusharthaBreakdown';
import SectionHeader from '../components/SectionHeader';
import NorthIndianChart from '../components/NorthIndianChart';
import SouthIndianChart from '../components/SouthIndianChart';
import TimeEngine from '../components/TimeEngine';
import WebPageContainer from '../components/WebPageContainer';
import useIsWideScreen from '../hooks/useIsWideScreen';
import { CHART_LABELS } from '../constants/astro';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useKundaliStore } from '../store/useKundaliStore';
import { useUserStore } from '../store/useUserStore';
import { ChartType, CurrentDasha, DailyReading } from '../types/kundali';
import { colors, radius, spacing, typography } from '../theme/theme';

const CHART_TYPES: ChartType[] = ['D1', 'D9', 'D10'];
const PREMIUM_CHARTS: ChartType[] = ['D9', 'D10'];

export default function ChartsScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const language = toContentLanguage(useUserStore((s) => s.language));
  const isPremium = useUserStore((s) => s.isPremium);
  const chartStyle = useUserStore((s) => s.chartStyle);
  const setChartStyle = useUserStore((s) => s.setChartStyle);
  const [selected, setSelected] = useState<ChartType>('D1');
  const isWide = useIsWideScreen();
  const chartSize = isWide ? 420 : 300;

  const chart = useKundaliStore((s) => s.charts[selected]?.[language]);
  const loading = useKundaliStore((s) => s.chartLoading);
  const error = useKundaliStore((s) => s.chartError);
  const fetchChart = useKundaliStore((s) => s.fetchChart);

  const identity = useKundaliStore((s) => s.identity);
  const fetchIdentity = useKundaliStore((s) => s.fetchIdentity);

  // Layer 3 (Time Engine) needs the current dasha stack + today's reading —
  // both cheap, already-built endpoints, fetched locally the same way
  // PeriodAnalysisScreen already does rather than adding more global store
  // state for data only this section uses.
  const [currentDasha, setCurrentDasha] = useState<CurrentDasha | null>(null);
  const [dailyReading, setDailyReading] = useState<DailyReading | null>(null);

  const isLocked = PREMIUM_CHARTS.includes(selected) && !isPremium;

  useEffect(() => {
    if (!isLocked) fetchChart(selected, language);
  }, [selected, language, isLocked]);

  useEffect(() => {
    fetchIdentity();
  }, []);

  useEffect(() => {
    getCurrentDasha().then(setCurrentDasha).catch(() => setCurrentDasha(null));
    getDailyReading(language).then(setDailyReading).catch(() => setDailyReading(null));
  }, [language]);

  return (
    <WebPageContainer style={styles.webContainer}>
    <ScrollView contentContainerStyle={styles.content}>
      {identity && <IdentityBasics identity={identity} language={language} />}

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

      <PrimaryButton
        label={t('chartLookup.entryPoint')}
        variant="outline"
        onPress={() => navigation.navigate('ChartLookup')}
      />

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
            <View style={styles.styleToggle}>
              <Pressable
                onPress={() => setChartStyle('north')}
                style={[styles.styleToggleButton, chartStyle === 'north' && styles.styleToggleButtonActive]}
              >
                <Text style={[styles.styleToggleText, chartStyle === 'north' && styles.styleToggleTextActive]}>
                  {t('charts.northIndianStyle')}
                </Text>
              </Pressable>
              <Pressable
                onPress={() => setChartStyle('south')}
                style={[styles.styleToggleButton, chartStyle === 'south' && styles.styleToggleButtonActive]}
              >
                <Text style={[styles.styleToggleText, chartStyle === 'south' && styles.styleToggleTextActive]}>
                  {t('charts.southIndianStyle')}
                </Text>
              </Pressable>
            </View>
            <View style={styles.chartWrap}>
              {chartStyle === 'north' ? (
                <NorthIndianChart chart={chart} language={language} size={chartSize} />
              ) : (
                <SouthIndianChart chart={chart} language={language} size={chartSize} />
              )}
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

          <Card>
            <SectionHeader title={t('charts.yogasTitle')} />
            <Text style={styles.yogasSubtitle}>{t('charts.yogasSubtitle')}</Text>
            <YogaFindingsList chart={chart} language={language} />
          </Card>

          {selected === 'D1' ? (
            <PurusharthaBreakdown chart={chart} language={language} />
          ) : (
            <Card>
              <SectionHeader title={t('charts.houseByHouseTitle')} />
              <Text style={styles.yogasSubtitle}>{t('charts.houseByHouseSubtitle')}</Text>
              <HouseBreakdownList chart={chart} language={language} />
            </Card>
          )}

          {currentDasha && dailyReading && (
            <TimeEngine currentDasha={currentDasha} dailyReading={dailyReading} language={language} />
          )}
        </>
      )}
    </ScrollView>
    </WebPageContainer>
  );
}

const styles = StyleSheet.create({
  webContainer: {
    flex: 1,
  },
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
    color: colors.textOnPrimary,
  },
  chartTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  chartCard: {
    alignItems: 'center',
  },
  styleToggle: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    padding: spacing.xs,
    alignSelf: 'stretch',
  },
  styleToggleButton: {
    flex: 1,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
  },
  styleToggleButtonActive: {
    backgroundColor: colors.primary,
  },
  styleToggleText: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  styleToggleTextActive: {
    color: colors.textOnPrimary,
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
