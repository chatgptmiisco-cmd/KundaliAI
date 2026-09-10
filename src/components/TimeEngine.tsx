import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import Card from './Card';
import { PLANET_NAMES } from '../constants/astro';
import { CurrentDasha, DailyReading } from '../types/kundali';
import { colors, radius, spacing, typography } from '../theme/theme';

interface Props {
  currentDasha: CurrentDasha;
  dailyReading: DailyReading;
  language: 'en' | 'hi';
}

function elapsedPercent(startIso: string, endIso: string): number {
  const start = new Date(startIso).getTime();
  const end = new Date(endIso).getTime();
  const now = Date.now();
  if (end <= start) return 0;
  return Math.max(0, Math.min(100, Math.round(((now - start) / (end - start)) * 100)));
}

export default function TimeEngine({ currentDasha, dailyReading, language }: Props) {
  const { t } = useTranslation();
  const names = PLANET_NAMES[language];

  const mahaPercent = elapsedPercent(currentDasha.mahadasha.startDate, currentDasha.mahadasha.endDate);
  const antarPercent = elapsedPercent(currentDasha.antardasha.startDate, currentDasha.antardasha.endDate);

  const sadeSati = dailyReading.doshas.find((d) => d.key === 'sade_sati');
  const jupiterActive = dailyReading.jupiterTransitingMoonSign;

  return (
    <Card>
      <Text style={styles.title}>{t('charts.timeEngine.title')}</Text>

      <Text style={styles.sectionLabel}>{t('charts.timeEngine.dashaSectionTitle')}</Text>
      <Text style={styles.dashaLabel}>{t('charts.timeEngine.mahadashaLabel', { lord: names[currentDasha.mahadasha.planet] })}</Text>
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${mahaPercent}%` }]} />
      </View>
      <Text style={styles.progressCaption}>{t('charts.timeEngine.elapsedLabel', { percent: mahaPercent })}</Text>

      <Text style={[styles.dashaLabel, styles.antardashaLabel]}>
        {t('charts.timeEngine.antardashaLabel', { lord: names[currentDasha.antardasha.planet] })}
      </Text>
      <View style={[styles.progressTrack, styles.progressTrackSmall]}>
        <View style={[styles.progressFillSmall, { width: `${antarPercent}%` }]} />
      </View>

      {/* What this period actually does — led with, not just the bare
          progress bars — reusing the daily reading's already-computed
          period_type and dominant_life_area rather than just naming lords. */}
      <Text style={styles.periodEffect}>
        {t(`charts.timeEngine.periodType.${dailyReading.periodType}`)}
      </Text>
      <Text style={styles.periodEffect}>
        {t('charts.timeEngine.dominantLifeArea', { area: dailyReading.dominantLifeArea })}
      </Text>

      <Text style={[styles.sectionLabel, styles.transitSectionLabel]}>{t('charts.timeEngine.transitSectionTitle')}</Text>
      {sadeSati?.isPresent && (
        <View style={styles.alertCard}>
          <Text style={styles.alertText}>
            {t('charts.timeEngine.sadeSatiActive', { phase: sadeSati.label })}
          </Text>
        </View>
      )}
      {jupiterActive && (
        <View style={[styles.alertCard, styles.alertCardFavourable]}>
          <Text style={styles.alertText}>{t('charts.timeEngine.jupiterActive')}</Text>
        </View>
      )}
      {!sadeSati?.isPresent && !jupiterActive && (
        <Text style={styles.noTransitText}>{t('charts.timeEngine.noMajorTransit')}</Text>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  title: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  sectionLabel: {
    ...typography.bodyBold,
    color: colors.textPrimary,
  },
  transitSectionLabel: {
    marginTop: spacing.lg,
  },
  dashaLabel: {
    ...typography.body,
    color: colors.textSecondary,
    marginTop: spacing.sm,
  },
  antardashaLabel: {
    marginTop: spacing.md,
  },
  progressTrack: {
    height: 14,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
    marginTop: spacing.xs,
    overflow: 'hidden',
  },
  progressTrackSmall: {
    height: 10,
  },
  progressFill: {
    height: '100%',
    backgroundColor: colors.primary,
    borderRadius: radius.pill,
  },
  progressFillSmall: {
    height: '100%',
    backgroundColor: colors.accent,
    borderRadius: radius.pill,
  },
  progressCaption: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: spacing.xs,
  },
  periodEffect: {
    ...typography.body,
    color: colors.textPrimary,
    marginTop: spacing.sm,
  },
  alertCard: {
    backgroundColor: colors.premiumLight,
    borderRadius: radius.md,
    padding: spacing.sm,
    marginTop: spacing.sm,
  },
  alertCardFavourable: {
    backgroundColor: colors.successLight,
  },
  alertText: {
    ...typography.body,
    color: colors.textPrimary,
  },
  noTransitText: {
    ...typography.body,
    color: colors.textSecondary,
    marginTop: spacing.sm,
  },
});
