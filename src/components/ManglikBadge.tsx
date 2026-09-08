import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { colors, elevation, radius, spacing, typography } from '../theme/theme';

interface Props {
  statusLine: string;
  size?: 'large' | 'medium';
}

// Deliberately calm: amber tones only, a neutral planet icon (never red,
// never a warning triangle) — Manglik is a factor to understand, not a
// verdict to fear.
export default function ManglikBadge({ statusLine, size = 'large' }: Props) {
  return (
    <View style={styles.wrap}>
      <View style={styles.iconCircle}>
        <Ionicons name="planet-outline" size={size === 'large' ? 26 : 22} color={colors.accentDark} />
      </View>
      <Text style={[size === 'large' ? typography.statusLine : typography.bodyBold, styles.text]}>
        {statusLine}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.accentLight,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.accent,
    padding: spacing.md,
    gap: spacing.md,
    ...elevation.card,
  },
  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    ...elevation.card,
  },
  text: {
    color: colors.accentDark,
    flexShrink: 1,
  },
});
