import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { colors, elevation, radius, spacing } from '../theme/theme';

export default function Card({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: ViewStyle;
}) {
  return <View style={[styles.card, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    ...elevation.card,
  },
});
