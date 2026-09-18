import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { lookupChart } from '../api/client';
import BirthDataFields from '../components/BirthDataFields';
import Card from '../components/Card';
import ErrorState from '../components/ErrorState';
import LoadingState from '../components/LoadingState';
import NorthIndianChart from '../components/NorthIndianChart';
import PlanetPositionsTable from '../components/PlanetPositionsTable';
import PremiumLockNotice from '../components/PremiumLockNotice';
import PrimaryButton from '../components/PrimaryButton';
import SouthIndianChart from '../components/SouthIndianChart';
import { CHART_LABELS } from '../constants/astro';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useUserStore } from '../store/useUserStore';
import { BirthChart, BirthData, ChartType } from '../types/kundali';
import { colors, radius, spacing, typography } from '../theme/theme';

const emptyPerson: BirthData = { name: '', dateOfBirth: '', timeOfBirth: '', placeOfBirth: '' };
const CHART_TYPES: ChartType[] = ['D1', 'D9', 'D10'];
const PREMIUM_CHARTS: ChartType[] = ['D9', 'D10'];

/** Product ask: "let me check someone else's chart" (a family member's,
 * say) without overwriting the signed-in user's own saved birth profile —
 * see api/client.ts's lookupChart for why this is a stateless, uncached
 * backend call. Deliberately its own screen rather than a mode inside
 * ChartsScreen: that screen's data all comes from useKundaliStore (keyed
 * to the user's own saved profile), and this one needs to hold an
 * arbitrary, throwaway BirthChart instead. */
export default function ChartLookupScreen() {
  const { t } = useTranslation();
  const language = toContentLanguage(useUserStore((s) => s.language));
  const isPremium = useUserStore((s) => s.isPremium);
  const chartStyle = useUserStore((s) => s.chartStyle);
  const setChartStyle = useUserStore((s) => s.setChartStyle);

  const [person, setPerson] = useState<BirthData>(emptyPerson);
  const [selectedType, setSelectedType] = useState<ChartType>('D1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [chart, setChart] = useState<BirthChart | null>(null);

  const canSubmit = person.dateOfBirth.trim() && person.timeOfBirth.trim() && person.placeOfBirth.trim();
  const isLocked = PREMIUM_CHARTS.includes(selectedType) && !isPremium;

  const runLookup = async (type: ChartType) => {
    setLoading(true);
    setError(false);
    try {
      setChart(await lookupChart(person, type, language));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  const handleView = () => {
    setSelectedType('D1');
    runLookup('D1');
  };

  const handleSelectType = (type: ChartType) => {
    setSelectedType(type);
    if (!PREMIUM_CHARTS.includes(type) || isPremium) runLookup(type);
  };

  if (!chart) {
    return (
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.subtitle}>{t('chartLookup.formSubtitle')}</Text>
        <Card>
          <BirthDataFields value={person} onChange={setPerson} />
        </Card>
        <PrimaryButton label={t('chartLookup.viewButton')} onPress={handleView} disabled={!canSubmit} />
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      {!!person.name.trim() && <Text style={styles.personName}>{person.name}</Text>}

      <View style={styles.tabs}>
        {CHART_TYPES.map((type) => {
          const active = type === selectedType;
          return (
            <Pressable
              key={type}
              onPress={() => handleSelectType(type)}
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

      {isLocked && (
        <PremiumLockNotice message={t('charts.lockedMessage')} unlockLabel={t('charts.unlockButton')} />
      )}

      {!isLocked && loading && <LoadingState message={t('common.loading')} />}

      {!isLocked && !loading && error && (
        <ErrorState
          title={t('kundali.errorTitle')}
          message={t('kundali.errorMessage')}
          onRetry={() => runLookup(selectedType)}
        />
      )}

      {!isLocked && !loading && !error && (
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
                <NorthIndianChart chart={chart} language={language} size={300} />
              ) : (
                <SouthIndianChart chart={chart} language={language} size={300} />
              )}
            </View>
          </Card>

          <Card>
            <PlanetPositionsTable chart={chart} language={language} />
          </Card>
        </>
      )}

      <PrimaryButton label={t('chartLookup.checkAnother')} variant="outline" onPress={() => setChart(null)} />
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
  personName: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
  },
  tabs: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    padding: spacing.xs,
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
});
