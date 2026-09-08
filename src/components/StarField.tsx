import React, { useEffect, useMemo, useRef } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';

/** A handful of small dots that twinkle and drift very slowly and randomly —
 * a quiet animated backdrop for dark "cosmic" screens (Welcome, kundali
 * generation). Purely decorative, so it renders behind everything and
 * ignores touches. */

function Star({ top, left, size, twinkleDuration, driftX, driftY, driftDuration }: {
  top: number;
  left: number;
  size: number;
  twinkleDuration: number;
  driftX: number;
  driftY: number;
  driftDuration: number;
}) {
  const opacity = useRef(new Animated.Value(0.15)).current;
  const drift = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const twinkle = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.9, duration: twinkleDuration, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.15, duration: twinkleDuration, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ]),
    );
    const move = Animated.loop(
      Animated.sequence([
        Animated.timing(drift, { toValue: 1, duration: driftDuration, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(drift, { toValue: 0, duration: driftDuration, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ]),
    );
    twinkle.start();
    move.start();
    return () => {
      twinkle.stop();
      move.stop();
    };
  }, []);

  const translateX = drift.interpolate({ inputRange: [0, 1], outputRange: [0, driftX] });
  const translateY = drift.interpolate({ inputRange: [0, 1], outputRange: [0, driftY] });

  return (
    <Animated.View
      style={{
        position: 'absolute',
        top: `${top}%`,
        left: `${left}%`,
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: '#fff',
        opacity,
        transform: [{ translateX }, { translateY }],
      }}
    />
  );
}

export default function StarField({ count = 28 }: { count?: number }) {
  const stars = useMemo(
    () =>
      Array.from({ length: count }, () => ({
        top: Math.random() * 100,
        left: Math.random() * 100,
        size: 1 + Math.random() * 2,
        twinkleDuration: 1500 + Math.random() * 2500,
        driftX: (Math.random() - 0.5) * 26,
        driftY: (Math.random() - 0.5) * 26,
        driftDuration: 12000 + Math.random() * 14000,
      })),
    [count],
  );

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      {stars.map((s, i) => (
        <Star key={i} {...s} />
      ))}
    </View>
  );
}
