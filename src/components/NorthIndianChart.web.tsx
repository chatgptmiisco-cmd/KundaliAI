import { LinearGradient } from 'expo-linear-gradient';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';
import { OUTER_PLANET_COLORS, PLANET_COLORS } from '../constants/astro';
import { BirthChart, Language } from '../types/kundali';
import { colors, fontFamily, radius } from '../theme/theme';

interface Props {
  chart: BirthChart;
  language: Language;
  size?: number;
}

// Metro/Expo automatically serves THIS file instead of NorthIndianChart.tsx
// for any `import NorthIndianChart from '.../NorthIndianChart'` when the
// platform is web (same ".web.tsx" convention this codebase already uses
// for DateTimeField.web.tsx) — every existing call site (ChartsScreen,
// ChartLookupScreen, CompleteKundaliScreen) needs zero changes, and native
// keeps importing the unchanged straight-line NorthIndianChart.tsx.
//
// Same data/topology as the native chart — SAME HOUSE_CENTROID positions
// (see that file's docstring for why house 1 is the top tip, counter-
// clockwise), same houseSignIndex/chipsInHouse logic, same planet colors —
// only the line-drawing technique differs: curved SVG paths instead of
// straight rotated Views, echoing the reference screenshot's scalloped/
// petal diamond silhouette, but in this app's own dark-purple/gold
// "Astrolabe Glass" palette rather than a literal copy of that reference's
// cream/orange skin.
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

// The 6 inner structural lines (2 diagonals + the 4 sides of the inner
// diamond) — identical segments to the native chart's LINES, just drawn as
// curves here instead of straight rotated Views.
const INNER_LINES: [number, number, number, number][] = [
  [0, 0, 1, 1],
  [1, 0, 0, 1],
  [0.5, 0, 1, 0.5],
  [1, 0.5, 0.5, 1],
  [0.5, 1, 0, 0.5],
  [0, 0.5, 0.5, 0],
];
// The 4 outer square edges, bowed gently outward instead — together with
// the inner lines' inward bow, this is what gives the whole silhouette its
// flower/petal read instead of a plain diamond-in-a-box.
const OUTER_EDGES: [number, number, number, number][] = [
  [0, 0, 1, 0],
  [1, 0, 1, 1],
  [1, 1, 0, 1],
  [0, 1, 0, 0],
];
const CENTER: [number, number] = [0.5, 0.5];
const INNER_CURVATURE = 0.32; // fraction of the way from each line's midpoint toward the center
const OUTER_CURVATURE = 0.12; // fraction of the way from each edge's midpoint AWAY from the center

function curvedPath(
  [x1, y1, x2, y2]: [number, number, number, number],
  size: number,
  curvature: number,
  direction: 1 | -1,
): string {
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;
  const controlX = midX + direction * curvature * (CENTER[0] - midX);
  const controlY = midY + direction * curvature * (CENTER[1] - midY);
  return `M ${x1 * size} ${y1 * size} Q ${controlX * size} ${controlY * size} ${x2 * size} ${y2 * size}`;
}

const ELEMENT_COLOR_BY_SIGN = [
  colors.accent, '#6B8E4E', '#7C8FBE', '#4D7C8A',
  colors.accent, '#6B8E4E', '#7C8FBE', '#4D7C8A',
  colors.accent, '#6B8E4E', '#7C8FBE', '#4D7C8A',
];

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
        <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
          {OUTER_EDGES.map((edge, i) => (
            <Path key={`outer-${i}`} d={curvedPath(edge, size, OUTER_CURVATURE, 1)} stroke={colors.primaryLight} strokeWidth={1.5} fill="none" />
          ))}
          {INNER_LINES.map((line, i) => (
            <Path key={`inner-${i}`} d={curvedPath(line, size, INNER_CURVATURE, -1)} stroke={colors.primary} strokeWidth={1.75} fill="none" />
          ))}
          <Circle cx={size / 2} cy={size / 2} r={5} fill={colors.primary} />
        </Svg>

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
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  jewel: {
    position: 'absolute',
    borderRadius: 4,
    transform: [{ rotate: '45deg' }],
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
