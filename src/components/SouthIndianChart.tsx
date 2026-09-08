import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import {
  houseNumberForSign,
  PLANET_COLORS,
  PLANET_GLYPHS,
  RING_CELL,
  RING_SIGN_INDEX,
  SIGN_GLYPHS,
  SIGN_NAMES,
} from '../constants/astro';
import { BirthChart, PlanetKey } from '../types/kundali';
import { colors, elevation, fontFamily, radius, spacing, typography } from '../theme/theme';

interface Props {
  chart: BirthChart;
  language: 'en' | 'hi';
  size?: number;
}

export default function SouthIndianChart({ chart, language, size = 320 }: Props) {
  const cellSize = size / 4;
  const signNames = SIGN_NAMES[language];
  const lagnaSignName = signNames[chart.lagnaSignIndex];

  const planetsBySign: Record<number, PlanetKey[]> = {};
  (Object.keys(chart.planetSignIndex) as PlanetKey[]).forEach((planet) => {
    const signIndex = chart.planetSignIndex[planet];
    if (!planetsBySign[signIndex]) planetsBySign[signIndex] = [];
    planetsBySign[signIndex].push(planet);
  });

  return (
    <View style={[styles.wrap, { width: size, height: size }]}>
      {RING_SIGN_INDEX.map((signIndex, ringPos) => {
        const [row, col] = RING_CELL[ringPos];
        const houseNumber = houseNumberForSign(signIndex, chart.lagnaSignIndex);
        const isLagna = houseNumber === 1;
        const planets = planetsBySign[signIndex] ?? [];

        return (
          <View
            key={signIndex}
            style={[
              styles.cell,
              {
                left: col * cellSize,
                top: row * cellSize,
                width: cellSize,
                height: cellSize,
              },
              isLagna && styles.lagnaCell,
            ]}
          >
            <View style={styles.cellTopRow}>
              <View style={[styles.houseBadge, isLagna && styles.lagnaBadge]}>
                <Text style={[styles.houseBadgeText, isLagna && styles.lagnaBadgeText]}>{houseNumber}</Text>
              </View>
              {isLagna && (
                <View style={styles.ascTag}>
                  <Text style={styles.ascTagText}>ASC</Text>
                </View>
              )}
            </View>

            <Text style={styles.signLabel} numberOfLines={1}>
              {SIGN_GLYPHS[signIndex]} {signNames[signIndex]}
            </Text>

            {planets.length > 0 && (
              <View style={styles.planetRow}>
                {planets.map((planet) => (
                  <View key={planet} style={[styles.planetChip, { borderColor: PLANET_COLORS[planet] }]}>
                    <Text style={[styles.planetGlyph, { color: PLANET_COLORS[planet] }]}>
                      {PLANET_GLYPHS[planet]}
                    </Text>
                    {chart.planetRetrograde[planet] && <Text style={styles.retrogradeMark}>℞</Text>}
                  </View>
                ))}
              </View>
            )}
          </View>
        );
      })}

      <View
        style={[
          styles.centerBox,
          { left: cellSize, top: cellSize, width: cellSize * 2, height: cellSize * 2 },
        ]}
      >
        <Text style={styles.centerType}>{chart.type}</Text>
        <View style={styles.centerDivider} />
        <Text style={styles.centerLagnaLabel}>{language === 'hi' ? 'लग्न' : 'Lagna'}</Text>
        <Text style={styles.centerLagnaSign}>
          {SIGN_GLYPHS[chart.lagnaSignIndex]} {lagnaSignName}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderWidth: 2,
    borderColor: colors.primary,
    borderRadius: radius.md,
    position: 'relative',
    backgroundColor: colors.surface,
    shadowColor: elevation.raised.shadowColor,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: elevation.raised.shadowOpacity,
    shadowRadius: elevation.raised.shadowRadius,
    elevation: elevation.raised.elevation,
  },
  cell: {
    position: 'absolute',
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.xs,
  },
  lagnaCell: {
    backgroundColor: colors.accentLight,
    borderColor: colors.accent,
    borderWidth: 1.5,
  },
  cellTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  houseBadge: {
    width: 18,
    height: 18,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  lagnaBadge: {
    backgroundColor: colors.accent,
  },
  houseBadgeText: {
    fontSize: 10,
    fontFamily: fontFamily.bold,
    color: colors.textSecondary,
  },
  lagnaBadgeText: {
    color: colors.textInverse,
  },
  ascTag: {
    backgroundColor: colors.accentDark,
    borderRadius: radius.sm,
    paddingHorizontal: 4,
    paddingVertical: 1,
  },
  ascTagText: {
    fontSize: 8,
    fontFamily: fontFamily.bold,
    color: colors.textInverse,
  },
  signLabel: {
    fontSize: 11,
    color: colors.textSecondary,
    marginTop: 2,
  },
  planetRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 3,
    marginTop: 3,
  },
  planetChip: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: 3,
    paddingVertical: 1,
    backgroundColor: colors.surface,
  },
  planetGlyph: {
    fontSize: 13,
    fontFamily: fontFamily.bold,
  },
  retrogradeMark: {
    fontSize: 9,
    color: colors.premium,
    marginLeft: 1,
  },
  centerBox: {
    position: 'absolute',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceMuted,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  centerType: {
    ...typography.sectionTitle,
    color: colors.primary,
  },
  centerDivider: {
    width: '40%',
    height: 1,
    backgroundColor: colors.border,
    marginVertical: 2,
  },
  centerLagnaLabel: {
    fontSize: 10,
    color: colors.textSecondary,
  },
  centerLagnaSign: {
    fontSize: 13,
    fontFamily: fontFamily.bold,
    color: colors.textPrimary,
  },
});
