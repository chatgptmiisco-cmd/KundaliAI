import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { PLANET_GLYPHS, PLANET_NAMES, PLANET_ORDER, SIGN_NAMES } from '../constants/astro';
import { BirthChart, Language } from '../types/kundali';
import { colors, fontFamily, radius, spacing, typography } from '../theme/theme';

/** Real per-planet "Grah Spashta" detail: exact degree (D1 only), nakshatra +
 * pada, house, and dignity — the concrete calculated facts a printed kundali
 * shows, not narrative prose. */
export default function PlanetPositionsTable({ chart, language }: { chart: BirthChart; language: Language }) {
  const { t } = useTranslation();
  const signNames = SIGN_NAMES[language];
  const planetNames = PLANET_NAMES[language];

  return (
    <View>
      {chart.lagnaDegreeDisplay && (
        <View style={styles.lagnaRow}>
          <Text style={styles.lagnaLabel}>{t('kundali.lagnaDegreeLabel')}</Text>
          <Text style={styles.lagnaValue}>
            {signNames[chart.lagnaSignIndex]} {chart.lagnaDegreeDisplay}
          </Text>
        </View>
      )}
      {PLANET_ORDER.map((planet) => {
        const detail = chart.planetDetails[planet];
        if (!detail) return null;
        return (
          <View key={planet} style={styles.row}>
            <View style={styles.glyphCircle}>
              <Text style={styles.glyph}>{PLANET_GLYPHS[planet]}</Text>
            </View>
            <View style={styles.rowText}>
              <View style={styles.rowTopLine}>
                <Text style={styles.planetName}>{planetNames[planet]}</Text>
                <Text style={styles.signDegree}>
                  {signNames[detail.signIndex]}
                  {detail.degreeDisplay ? ` ${detail.degreeDisplay}` : ''}
                  {detail.retrograde ? ' ℞' : ''}
                </Text>
              </View>
              <Text style={styles.rowSubLine}>
                {t('kundali.houseLabel')} {detail.house}
                {detail.nakshatraName ? ` · ${detail.nakshatraName}` : ''}
                {detail.nakshatraPada ? `-${detail.nakshatraPada}` : ''}
                {detail.dignity && detail.dignity !== 'neutral' ? ` · ${t(`kundali.dignity.${detail.dignity}`)}` : ''}
              </Text>
            </View>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  lagnaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: spacing.sm,
    marginBottom: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  lagnaLabel: {
    ...typography.bodyBold,
    color: colors.textSecondary,
  },
  lagnaValue: {
    ...typography.bodyBold,
    color: colors.primary,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.xs,
  },
  glyphCircle: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
  },
  glyph: {
    fontSize: 18,
    color: colors.primary,
  },
  rowText: {
    flex: 1,
  },
  rowTopLine: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  planetName: {
    ...typography.bodyBold,
    color: colors.textPrimary,
  },
  signDegree: {
    ...typography.body,
    color: colors.textPrimary,
    fontFamily: fontFamily.medium,
  },
  rowSubLine: {
    ...typography.caption,
    color: colors.textSecondary,
  },
});
