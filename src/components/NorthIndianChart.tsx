import { LinearGradient } from 'expo-linear-gradient';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { OUTER_PLANET_COLORS, PLANET_COLORS } from '../constants/astro';
import { BirthChart, Language } from '../types/kundali';
import { colors, fontFamily, radius } from '../theme/theme';

interface Props {
  chart: BirthChart;
  language: Language;
  size?: number;
}

/** Fixed centroid (as a fraction 0-1 of the square's side) for each of the
 * 12 house positions in a traditional North Indian diamond chart. House
 * *position* never moves — only which sign/planets occupy it changes with
 * the Lagna — matching the real convention (unlike the South Indian style,
 * where signs are fixed and houses rotate). Derived from the chart's
 * geometry: the outer square's two diagonals plus the diamond connecting
 * its edge-midpoints together carve it into 4 "tip" quadrilaterals (houses
 * 1/4/7/10, the Kendras, sitting at the top/left/bottom/right points) and 8
 * corner triangles (the remaining houses, two flanking each tip).
 *
 * House 1 is always the top tip, and from there the real convention reads
 * COUNTER-CLOCKWISE, not clockwise (verified against Wikipedia's Kuṇḍali
 * article: "the other bhāva-s follow it, counter-clockwise, in the sequence
 * of the zodiac" — an earlier version of this array went clockwise instead,
 * which put every Kendra house except 1/7 on the wrong side and read as a
 * mirror-image chart next to any standard reference). House 4 therefore
 * sits at the LEFT tip and house 10 at the RIGHT tip, not the reverse. */
const HOUSE_CENTROID: [number, number][] = [
  [0.5, 0.25], // 1 - top tip (Kendra)
  [0.25, 0.083], // 2
  [0.083, 0.25], // 3
  [0.25, 0.5], // 4 - left tip (Kendra)
  [0.083, 0.75], // 5
  [0.25, 0.917], // 6
  [0.5, 0.75], // 7 - bottom tip (Kendra)
  [0.75, 0.917], // 8
  [0.917, 0.75], // 9
  [0.75, 0.5], // 10 - right tip (Kendra)
  [0.917, 0.25], // 11
  [0.75, 0.083], // 12
];
const KENDRA_HOUSES = new Set([1, 4, 7, 10]);

// The 6 line segments (2 outer diagonals + the 4 sides of the inner
// diamond) that, together with the outer square border, form the classic
// diamond layout. Each is [x1, y1, x2, y2] as a fraction of the square side.
const LINES: [number, number, number, number][] = [
  [0, 0, 1, 1], // top-left to bottom-right diagonal
  [1, 0, 0, 1], // top-right to bottom-left diagonal
  [0.5, 0, 1, 0.5], // top-mid to right-mid
  [1, 0.5, 0.5, 1], // right-mid to bottom-mid
  [0.5, 1, 0, 0.5], // bottom-mid to left-mid
  [0, 0.5, 0.5, 0], // left-mid to top-mid
];

// Classical element per sign (Aries=fire ... repeating every 4 signs),
// tinted consistently with the Identity Basics element/modality breakdown
// elsewhere in the app — same four swatches, so the chart and that section
// read as one visual language rather than two unrelated colour choices.
const ELEMENT_COLOR_BY_SIGN = [
  colors.accent, '#6B8E4E', '#7C8FBE', '#4D7C8A', // Aries..Cancer
  colors.accent, '#6B8E4E', '#7C8FBE', '#4D7C8A', // Leo..Scorpio
  colors.accent, '#6B8E4E', '#7C8FBE', '#4D7C8A', // Sagittarius..Pisces
];

/** One chip's worth of render data — unifies the 9 classical grahas (from
 * houseBreakdown) with the 3 display-only outer planets (from
 * chart.outerPlanets) into one shape, since visually they're drawn exactly
 * the same way; only the color table and retrograde lookup differ. */
interface ChipData {
  code: string;
  color: string;
  retrograde: boolean;
}

export default function NorthIndianChart({ chart, language, size = 300 }: Props) {
  const houseSignIndex = (house: number) => (chart.lagnaSignIndex + house - 1) % 12;
  const chipsInHouse = (house: number): ChipData[] => {
    const grahas = chart.houseBreakdown.find((h) => h.house === house)?.planets ?? [];
    const outer = chart.outerPlanets.filter((p) => p.house === house);
    return [
      ...grahas.map((p) => ({ code: p, color: PLANET_COLORS[p], retrograde: !!chart.planetRetrograde[p] })),
      ...outer.map((p) => ({ code: p.planet, color: OUTER_PLANET_COLORS[p.planet], retrograde: p.retrograde })),
    ];
  };

  return (
    <View style={[styles.frame, { width: size + 16, height: size + 16 }]}>
      <LinearGradient
        colors={[colors.background, colors.surface]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[styles.square, { width: size, height: size }]}
      >
        {/* Diamond-tip accents behind the 4 Kendra houses (1/4/7/10) — a
            subtle rotated-square "jewel" tinted by that house's own sign
            element, marking the angular houses the way real charts often
            give the Lagna point special visual weight. */}
        {HOUSE_CENTROID.map(([fx, fy], idx) => {
          const house = idx + 1;
          if (!KENDRA_HOUSES.has(house)) return null;
          const signIndex = houseSignIndex(house);
          const jewel = 30;
          return (
            <View
              key={`jewel-${house}`}
              style={[
                styles.jewel,
                {
                  width: jewel,
                  height: jewel,
                  left: fx * size - jewel / 2,
                  top: fy * size - jewel / 2,
                  backgroundColor: ELEMENT_COLOR_BY_SIGN[signIndex],
                  opacity: 0.14,
                },
              ]}
            />
          );
        })}

        {LINES.map(([x1, y1, x2, y2], i) => {
          const dx = (x2 - x1) * size;
          const dy = (y2 - y1) * size;
          const length = Math.sqrt(dx * dx + dy * dy);
          const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
          const midX = ((x1 + x2) / 2) * size;
          const midY = ((y1 + y2) / 2) * size;
          return (
            <View
              key={i}
              style={[
                styles.line,
                {
                  width: length,
                  left: midX - length / 2,
                  top: midY - 0.9,
                  backgroundColor: colors.primary,
                  transform: [{ rotate: `${angle}deg` }],
                },
              ]}
            />
          );
        })}

        {HOUSE_CENTROID.map(([fx, fy], idx) => {
          const house = idx + 1;
          const signIndex = houseSignIndex(house);
          const chips = chipsInHouse(house);
          const isLagna = house === 1;
          return (
            <View
              key={house}
              style={[
                styles.houseCell,
                {
                  left: fx * size - 27,
                  top: fy * size - 24,
                },
              ]}
            >
              {isLagna && (
                <View style={styles.ascBadge}>
                  <Text style={styles.ascBadgeText}>ASC</Text>
                </View>
              )}
              {/* Deliberately only ONE number per cell — the sign's real
                  number (1=Aries..12=Pisces), the actual convention real
                  North Indian charts print (and far more reliably rendered
                  across devices than a Unicode zodiac glyph, which shows as
                  a blank box on plenty of Android fonts). An earlier version
                  also showed a house-number-from-Lagna badge here, which
                  made every cell carry two different 1-12 numbers at once —
                  correct individually, but read as "everything's scattered"
                  next to any reference chart (which shows only the sign
                  number) since there was no way to tell which number was
                  which at a glance. */}
              {/* High-contrast off-white rather than the muted per-element
                  tint below (which stays on the Kendra jewel glow only) —
                  the tint read as too low-contrast against the dark
                  background to scan at a glance, which was the other half
                  of the "signs aren't clearly visible" report. */}
              <Text style={styles.signNumber}>{signIndex + 1}</Text>
              <View style={styles.planetsRow}>
                {chips.map((chip) => (
                  <View key={chip.code} style={[styles.planetChip, { backgroundColor: `${chip.color}1F` }]}>
                    <Text style={[styles.planetName, { color: chip.color }]}>
                      {chip.code}
                      {chip.retrograde ? 'ᴿ' : ''}
                    </Text>
                  </View>
                ))}
              </View>
            </View>
          );
        })}
      </LinearGradient>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 8,
    borderWidth: 2.5,
    borderColor: colors.primary,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  square: {
    borderWidth: 1,
    borderColor: colors.primaryLight,
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  jewel: {
    position: 'absolute',
    borderRadius: 4,
    transform: [{ rotate: '45deg' }],
  },
  line: {
    position: 'absolute',
    height: 1.75,
  },
  houseCell: {
    position: 'absolute',
    width: 54,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 1,
  },
  ascBadge: {
    position: 'absolute',
    top: -16,
    backgroundColor: colors.accentDark,
    borderRadius: radius.pill,
    paddingHorizontal: 6,
    paddingVertical: 1,
  },
  ascBadgeText: {
    fontSize: 9,
    fontFamily: fontFamily.bold,
    color: colors.textInverse,
  },
  signNumber: {
    fontSize: 19,
    fontFamily: fontFamily.displayBold,
    marginTop: 6,
    color: colors.textPrimary,
  },
  planetsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 2,
    maxWidth: 56,
  },
  planetChip: {
    borderRadius: 4,
    paddingHorizontal: 3,
    paddingVertical: 1,
  },
  planetName: {
    fontSize: 11,
    fontFamily: fontFamily.bold,
  },
});
