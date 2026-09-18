import { LinearGradient } from 'expo-linear-gradient';
import React from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';
import { colors } from '../theme/theme';

interface Props {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}

/** The night-sky backdrop every screen sits on in the "Astrolabe Glass"
 * design — a diagonal wash from a violet nebula-glow corner down into the
 * deep indigo base, standing in for the mockup's radial-gradient glow
 * (React Native's LinearGradient has no radial mode without pulling in
 * react-native-svg just for this one effect). Wrap a screen's outermost
 * View in this instead of setting backgroundColor: colors.background
 * directly, wherever the fuller cosmic treatment (not just the flat dark
 * base color) is wanted. */
export default function CosmicBackground({ children, style }: Props) {
  return (
    <LinearGradient
      colors={['#2C1B45', '#1C1233', colors.background]}
      start={{ x: 0.1, y: 0 }}
      end={{ x: 0.9, y: 1 }}
      locations={[0, 0.45, 1]}
      style={[styles.fill, style]}
    >
      {children}
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
  },
});
