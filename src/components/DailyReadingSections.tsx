import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import BulletList from './BulletList';
import Card from './Card';
import SectionHeader from './SectionHeader';
import { DailyReading } from '../types/kundali';
import { colors, fontFamily, radius, spacing, typography } from '../theme/theme';

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

/** Every field the daily-reading engine computes, rendered as a stack of
 * cards — shared between the standalone "Today" detail screen and Home's
 * Today tab, so there is exactly one place that knows how to lay this out. */
export default function DailyReadingSections({ reading }: { reading: DailyReading }) {
  const { t } = useTranslation();

  const energyModeLabel = t(`horoscope.energyModes.${reading.energyMode}`, reading.energyMode);
  const periodTypeLabel = t(`horoscope.periodTypes.${reading.periodType}`, reading.periodType);
  const tithiLabel = t(`horoscope.tithiTags.${reading.tithiTag}`, reading.tithiTag);

  return (
    <>
      <Card>
        <Text style={styles.ratingNumber}>{reading.rating}/10</Text>
        <Text style={styles.ratingLabel}>{t('horoscope.todaysRatingLabel')}</Text>
        <Text style={styles.reasonText}>{reading.ratingReason}</Text>
        <View style={styles.tagsRow}>
          <View style={styles.tag}>
            <Text style={styles.tagText}>{reading.dominantTheme}</Text>
          </View>
          <View style={styles.tag}>
            <Text style={styles.tagText}>{energyModeLabel}</Text>
          </View>
          <View style={styles.tag}>
            <Text style={styles.tagText}>{tithiLabel}</Text>
          </View>
        </View>
        <View style={styles.luckyRow}>
          <View style={styles.luckyItem}>
            <Text style={styles.luckyLabel}>{t('horoscope.todaysColorLabel')}</Text>
            <View style={[styles.colorChip, { backgroundColor: colors.primaryLight }]}>
              <Text style={styles.colorChipText}>{reading.todayColor}</Text>
            </View>
          </View>
          <View style={styles.luckyItem}>
            <Text style={styles.luckyLabel}>{t('horoscope.todaysNumberLabel')}</Text>
            <View style={[styles.colorChip, { backgroundColor: colors.accentLight }]}>
              <Text style={styles.colorChipText}>{reading.luckyNumber}</Text>
            </View>
          </View>
        </View>
      </Card>

      <Card>
        <SectionHeader title={t('horoscope.todayGuidanceTitle')} />
        <BulletList items={reading.todayGuidance} />
      </Card>

      <Card style={styles.brutalTruthCard}>
        <Text style={styles.brutalTruthLabel}>{t('kundali.brutalTruthLabel')}</Text>
        <Text style={styles.brutalTruthText}>{reading.brutalTruth}</Text>
      </Card>

      <Card>
        <SectionHeader title={t('horoscope.riskOpportunityTitle')} />
        <InfoRow label={t('horoscope.keyRiskLabel')} value={reading.keyRisk} />
        <InfoRow label={t('horoscope.keyOpportunityLabel')} value={reading.keyOpportunity} />
      </Card>

      <Card>
        <SectionHeader title={t('horoscope.beforeYouLeaveHomeLabel')} />
        <BulletList items={reading.beforeYouLeaveHome} />
      </Card>

      <Card>
        <SectionHeader title={t('horoscope.doshasLabel')} />
        {reading.doshas.map((d) => (
          <View key={d.key} style={styles.doshaRow}>
            <Text style={styles.infoValue}>{d.label}</Text>
            <View style={[styles.doshaPill, d.isPresent ? styles.doshaPillActive : styles.doshaPillInactive]}>
              <Text style={[styles.doshaPillText, d.isPresent && styles.doshaPillTextActive]}>
                {d.isPresent ? t('horoscope.doshaPresent') : t('horoscope.doshaNotPresent')}
              </Text>
            </View>
          </View>
        ))}
      </Card>

      <Card>
        <SectionHeader title={t('horoscope.currentPeriodTitle')} />
        <InfoRow label={t('periods.screenTitle')} value={reading.mahadashaLabel} />
        <InfoRow label={t('horoscope.periodRatingLabel')} value={`${reading.periodRating}/10`} />
        <InfoRow label={t('horoscope.periodTypeLabel')} value={periodTypeLabel} />
        <InfoRow label={t('horoscope.dominantLifeAreaLabel')} value={reading.dominantLifeArea} />
      </Card>

      <Card>
        <SectionHeader title={t('horoscope.natalPatternsTitle')} />
        <InfoRow label={t('horoscope.coreStrengthLabel')} value={reading.coreStrength} />
        <InfoRow label={t('horoscope.coreWeaknessLabel')} value={reading.coreWeakness} />
        <InfoRow label={t('horoscope.stressPatternLabel')} value={reading.stressPattern} />
        <InfoRow label={t('horoscope.decisionStyleLabel')} value={reading.decisionStyle} />
      </Card>

      <Card>
        <SectionHeader title={t('horoscope.moonAndTransitTitle')} />
        <InfoRow label={t('horoscope.moonNakshatraLabel')} value={`${reading.moonNakshatra} — ${reading.moonMoodTag}`} />
        <InfoRow label={t('horoscope.transitHighlightLabel')} value={reading.transitHighlight} />
      </Card>

      <Card>
        <SectionHeader title={t('horoscope.lifeGrowthTaskLabel')} />
        <Text style={styles.reasonText}>{reading.lifeGrowthTask}</Text>
      </Card>
    </>
  );
}

const styles = StyleSheet.create({
  ratingNumber: {
    ...typography.display,
    color: colors.primary,
  },
  ratingLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  luckyRow: {
    flexDirection: 'row',
    gap: spacing.lg,
    marginTop: spacing.md,
  },
  luckyItem: {
    alignItems: 'flex-start',
  },
  luckyLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  colorChip: {
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  colorChipText: {
    ...typography.bodyBold,
    color: colors.textOnPrimary,
  },
  reasonText: {
    ...typography.body,
    color: colors.textPrimary,
  },
  tagsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginTop: spacing.sm,
  },
  tag: {
    backgroundColor: colors.background,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  tagText: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  brutalTruthCard: {
    backgroundColor: colors.primaryLight,
    borderColor: colors.primary,
  },
  brutalTruthLabel: {
    ...typography.caption,
    color: colors.textOnPrimary,
    fontFamily: fontFamily.bold,
    marginBottom: spacing.xs,
  },
  brutalTruthText: {
    ...typography.bodyBold,
    color: colors.textOnPrimary,
  },
  infoRow: {
    marginBottom: spacing.sm,
  },
  infoLabel: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  infoValue: {
    ...typography.body,
    color: colors.textPrimary,
  },
  doshaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  doshaPill: {
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  doshaPillActive: {
    backgroundColor: colors.premiumLight,
  },
  doshaPillInactive: {
    backgroundColor: colors.successLight,
  },
  doshaPillText: {
    ...typography.caption,
    color: colors.success,
    fontFamily: fontFamily.bold,
  },
  doshaPillTextActive: {
    color: colors.primaryDark,
  },
});
