import React, { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, Text, View } from 'react-native';
import { colors, fontFamily, spacing, typography } from '../theme/theme';

/** Three concentric rings, each spinning at its own speed/direction with a
 * small coloured "planet" riding the rim, and a slowly pulsing zodiac glyph
 * at the centre. Used everywhere the app needs a loading indicator — the
 * same motif at the splash screen, the kundali-generation screen, and every
 * plain inline spinner, just at different sizes. */

const RING_DOT_COLORS = [colors.accent, colors.success, colors.premium];
const CENTER_GLYPHS = ['☉', '☽', '♂', '☿', '♃', '♀', '♄'];

function useSpin(durationMs: number, reverse = false) {
  const value = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.timing(value, {
        toValue: 1,
        duration: durationMs,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [durationMs]);
  return value.interpolate({
    inputRange: [0, 1],
    outputRange: reverse ? ['360deg', '0deg'] : ['0deg', '360deg'],
  });
}

function usePulse() {
  const value = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(value, { toValue: 1.12, duration: 900, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(value, { toValue: 1, duration: 900, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, []);
  return value;
}

function useGlyphCycle(intervalMs: number) {
  const [index, setIndex] = React.useState(0);
  useEffect(() => {
    const timer = setInterval(() => setIndex((i) => (i + 1) % CENTER_GLYPHS.length), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return CENTER_GLYPHS[index];
}

interface Props {
  size?: number;
  dark?: boolean;
  message?: string;
}

export default function PlanetLoader({ size = 72, dark = false, message }: Props) {
  const spinOuter = useSpin(9000);
  const spinMid = useSpin(6500, true);
  const spinInner = useSpin(4200);
  const pulse = usePulse();
  const glyph = useGlyphCycle(650);

  const ringColor = dark ? 'rgba(255,255,255,0.16)' : 'rgba(122,59,46,0.14)';
  const coreBg = dark ? 'rgba(255,255,255,0.1)' : colors.primaryLight;
  const glyphColor = dark ? colors.textInverse : colors.primary;

  const dotSize = Math.max(5, size * 0.07);

  return (
    <View style={{ alignItems: 'center' }}>
      <View style={{ width: size, height: size }}>
        <Animated.View
          style={[
            styles.ring,
            { borderColor: ringColor, transform: [{ rotate: spinOuter }] },
          ]}
        >
          <View
            style={[
              styles.dot,
              { width: dotSize, height: dotSize, borderRadius: dotSize / 2, backgroundColor: RING_DOT_COLORS[0], top: -dotSize / 2 },
            ]}
          />
        </Animated.View>
        <Animated.View
          style={[
            styles.ring,
            {
              top: size * 0.12,
              left: size * 0.12,
              right: size * 0.12,
              bottom: size * 0.12,
              borderColor: ringColor,
              transform: [{ rotate: spinMid }],
            },
          ]}
        >
          <View
            style={[
              styles.dot,
              { width: dotSize * 0.85, height: dotSize * 0.85, borderRadius: dotSize / 2, backgroundColor: RING_DOT_COLORS[1], top: -dotSize * 0.42, left: '86%' },
            ]}
          />
        </Animated.View>
        <Animated.View
          style={[
            styles.ring,
            {
              top: size * 0.26,
              left: size * 0.26,
              right: size * 0.26,
              bottom: size * 0.26,
              borderColor: ringColor,
              transform: [{ rotate: spinInner }],
            },
          ]}
        >
          <View
            style={[
              styles.dot,
              { width: dotSize * 0.7, height: dotSize * 0.7, borderRadius: dotSize / 2, backgroundColor: RING_DOT_COLORS[2], top: '78%', left: -dotSize * 0.35 },
            ]}
          />
        </Animated.View>
        <View
          style={[
            styles.core,
            {
              top: size * 0.32,
              left: size * 0.32,
              right: size * 0.32,
              bottom: size * 0.32,
              backgroundColor: coreBg,
              borderRadius: (size * 0.36) / 2,
            },
          ]}
        >
          <Animated.Text style={[styles.glyph, { color: glyphColor, fontSize: size * 0.24, transform: [{ scale: pulse }] }]}>
            {glyph}
          </Animated.Text>
        </View>
      </View>
      {message && (
        <Text style={[styles.message, dark && styles.messageDark]} accessibilityRole="alert">
          {message}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  ring: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderWidth: 1,
    borderRadius: 999,
    alignItems: 'center',
  },
  dot: {
    position: 'absolute',
  },
  core: {
    position: 'absolute',
    alignItems: 'center',
    justifyContent: 'center',
  },
  glyph: {
    fontFamily: fontFamily.regular,
  },
  message: {
    ...typography.body,
    color: colors.textSecondary,
    marginTop: spacing.md,
    textAlign: 'center',
  },
  messageDark: {
    color: 'rgba(255,255,255,0.85)',
  },
});
