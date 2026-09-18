import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import {
  houseNumberForSign,
  OUTER_PLANET_COLORS,
  OUTER_PLANET_GLYPHS,
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

/** Unifies the 9 classical grahas with the 3 display-only outer planets
 * into one render shape — see NorthIndianChart's identical ChipData for
 * why (same reasoning, same split source data, different chart geometry). */
interface ChipData {
  key: string;
  glyph: string;
  color: string;
  retrograde: boolean;
}

export default function SouthIndianChart({ chart, language, size = 320 }: Props) {
  const cellSize = size / 4;
  const signNames = SIGN_NAMES[language];
  const lagnaSignName = signNames[chart.lagnaSignIndex];

  const chipsBySign: Record<number, ChipData[]> = {};
  (Object.keys(chart.planetSignIndex) as PlanetKey[]).forEach((planet) => {
    const signIndex = chart.planetSignIndex[planet];
    if (!chipsBySign[signIndex]) chipsBySign[signIndex] = [];
    chipsBySign[signIndex].push({
      key: planet,
      glyph: PLANET_GLYPHS[planet],
      color: PLANET_COLORS[planet],
      retrograde: !!chart.planetRetrograde[planet],
    });
  });
  chart.outerPlanets.forEach((p) => {
    if (!chipsBySign[p.signIndex]) chipsBySign[p.signIndex] = [];
    chipsBySign[p.signIndex].push({
      key: p.planet,
      glyph: OUTER_PLANET_GLYPHS[p.planet],
      color: OUTER_PLANET_COLORS[p.planet],
      retrograde: p.retrograde,
    });
  });

  return (
    <View style={[styles.wrap, { width: size, height: size }]}>
      {RING_SIGN_INDEX.map((signIndex, ringPos) => {
        const [row, col] = RING_CELL[ringPos];
        const houseNumber = houseNumberForSign(signIndex, chart.lagnaSignIndex);
        const isLagna = houseNumber === 1;
        const chips = chipsBySign[signIndex] ?? [];

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

            {chips.length > 0 && (
              <View style={styles.planetRow}>
                {chips.map((chip) => (
                  <View key={chip.key} style={[styles.planetChip, { borderColor: chip.color }]}>
                    <Text style={[styles.planetGlyph, { color: chip.color }]}>{chip.glyph}</Text>
                    {chip.retrograde && <Text style={styles.retrogradeMark}>℞</Text>}
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
