import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { PLANET_NAMES } from '../constants/astro';
import { BirthChart, Language } from '../types/kundali';
import { colors, fontFamily, radius, spacing, typography } from '../theme/theme';

/** The house-by-house "what's here and what it means" breakdown — real
 * placements turned into plain-language explanation instead of a bare
 * planet/sign table. */
export function HouseBreakdownList({ chart, language }: { chart: BirthChart; language: Language }) {
  const { t } = useTranslation();
  const planetNames = PLANET_NAMES[language];

  return (
    <View>
      {chart.houseBreakdown.map((house) => {
        const signName = language === 'hi' ? house.signNameHi : house.signNameEn;
        const explanation = language === 'hi' ? house.explanationHi : house.explanationEn;
        return (
          <View key={house.house} style={styles.houseRow}>
            <View style={styles.houseHeader}>
              <Text style={styles.houseNumber}>
                {t('kundali.houseLabel')} {house.house}
              </Text>
              <Text style={styles.houseSign}>{signName}</Text>
              {house.planets.length > 0 && (
                <Text style={styles.housePlanets}>
                  {house.planets.map((p) => planetNames[p]).join(', ')}
                </Text>
              )}
            </View>
            <Text style={styles.houseExplanation}>{explanation}</Text>
          </View>
        );
      })}
    </View>
  );
}

/** Detected classical yogas/doshas (Gajakesari, Panch Mahapurusha, a
 * conservative Raj Yoga, Manglik, Kaal Sarp, Kemadruma) — D1 only. */
export function YogaFindingsList({ chart, language }: { chart: BirthChart; language: Language }) {
  const { t } = useTranslation();

  if (chart.yogas.length === 0) {
    return <Text style={styles.noYogas}>{t('charts.noYogasFound')}</Text>;
  }

  return (
    <View>
      {chart.yogas.map((yoga) => (
        <View key={yoga.key} style={styles.yogaCard}>
          <Text style={styles.yogaName}>{language === 'hi' ? yoga.nameHi : yoga.nameEn}</Text>
          <Text style={styles.yogaDescription}>
            {language === 'hi' ? yoga.descriptionHi : yoga.descriptionEn}
          </Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  houseRow: {
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  houseHeader: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.xs,
  },
  houseNumber: {
    ...typography.bodyBold,
    color: colors.primary,
  },
  houseSign: {
    ...typography.bodyBold,
    color: colors.textPrimary,
  },
  housePlanets: {
    ...typography.caption,
    color: colors.accentDark,
    fontFamily: fontFamily.bold,
  },
  houseExplanation: {
    ...typography.body,
    color: colors.textSecondary,
  },
  noYogas: {
    ...typography.body,
    color: colors.textSecondary,
  },
  yogaCard: {
    backgroundColor: colors.premiumLight,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.premium,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  yogaName: {
    ...typography.bodyBold,
    color: colors.premium,
    marginBottom: spacing.xs,
  },
  yogaDescription: {
    ...typography.body,
    color: colors.textPrimary,
  },
});
