import React, { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';
import { colors, elevation, glass, radius, spacing } from '../theme/theme';

const DOT_COUNT = 3;
const BOUNCE_HEIGHT = 4;
const CYCLE_MS = 900;
// Each dot starts its bounce this many ms after the previous one — the
// classic WhatsApp/iMessage "fumbled dots" stagger, not all three moving
// in lockstep.
const STAGGER_MS = 150;

// Three dots bouncing in a rolling wave, matching the WhatsApp/iMessage
// "typing…" bubble convention — shown in place of a reply while the app is
// waiting on the real chart-backed answer (see RishiChatScreen's `phase`).
export default function TypingIndicator() {
  const dotAnims = useRef([...Array(DOT_COUNT)].map(() => new Animated.Value(0))).current;

  useEffect(() => {
    const loops = dotAnims.map((anim, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * STAGGER_MS),
          Animated.timing(anim, {
            toValue: 1,
            duration: CYCLE_MS / 2,
            easing: Easing.out(Easing.quad),
            useNativeDriver: true,
          }),
          Animated.timing(anim, {
            toValue: 0,
            duration: CYCLE_MS / 2,
            easing: Easing.in(Easing.quad),
            useNativeDriver: true,
          }),
          Animated.delay((DOT_COUNT - 1 - i) * STAGGER_MS),
        ])
      )
    );
    loops.forEach((loop) => loop.start());
    return () => loops.forEach((loop) => loop.stop());
  }, [dotAnims]);

  return (
    <View style={styles.bubble}>
      <View style={styles.dotsRow}>
        {dotAnims.map((anim, i) => (
          <Animated.View
            key={i}
            style={[
              styles.dot,
              {
                opacity: anim.interpolate({ inputRange: [0, 1], outputRange: [0.35, 1] }),
                transform: [
                  { translateY: anim.interpolate({ inputRange: [0, 1], outputRange: [0, -BOUNCE_HEIGHT] }) },
                ],
              },
            ]}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bubble: {
    alignSelf: 'flex-start',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: glass.borderSoft,
    borderRadius: radius.xl,
    borderBottomLeftRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 4,
    marginBottom: spacing.sm,
    shadowColor: elevation.card.shadowColor,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: elevation.card.shadowOpacity,
    shadowRadius: elevation.card.shadowRadius,
    elevation: elevation.card.elevation,
  },
  dotsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.textSecondary,
  },
});
