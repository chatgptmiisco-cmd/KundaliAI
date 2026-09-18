import { BlurView } from 'expo-blur';
import React from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';
import { colors, glass, radius } from '../theme/theme';

interface Props {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  /** Rounded (default, most cards) vs pill (composer bars, chips). */
  radius?: number;
}

/** The one frosted-glass surface every card/sheet/composer in the
 * "Astrolabe Glass" design sits on, instead of a flat colored rectangle —
 * see the approved design mockup (kundaliai_design_direction.html).
 *
 * Real blur only reliably applies on iOS with this simple setup — Android
 * needs a `BlurTargetView` wrapped around whatever sits BEHIND this (see
 * expo-blur's docs) to actually blur it, which would mean restructuring
 * every screen's background, not just this component. Until that's worth
 * doing, Android gets a plain tinted see-through layer instead of a
 * genuine blur — a graceful, non-broken fallback, not a crash, just less
 * "frosted" than iOS until we wire that up.
 */
export default function GlassSurface({ children, style, radius: r = radius.lg }: Props) {
  return (
    <View style={[styles.wrap, { borderRadius: r }, style]}>
      <BlurView intensity={glass.blurIntensity} tint="dark" style={StyleSheet.absoluteFill} />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    overflow: 'hidden',
    backgroundColor: glass.fill,
    borderWidth: 1,
    borderColor: glass.border,
    shadowColor: colors.shadow,
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.35,
    shadowRadius: 24,
    elevation: 6,
  },
});
