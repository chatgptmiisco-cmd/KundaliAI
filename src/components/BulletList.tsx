import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { colors, spacing, typography } from '../theme/theme';

export default function BulletList({ items }: { items: string[] }) {
  return (
    <View style={styles.wrap}>
      {items.map((item, idx) => (
        <View key={idx} style={styles.row}>
          <Text style={styles.dot}>•</Text>
          <Text style={styles.text}>{item}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: spacing.sm },
  row: {
    flexDirection: 'row',
    marginBottom: spacing.sm,
    paddingRight: spacing.sm,
  },
  dot: {
    ...typography.body,
    color: colors.primary,
    marginRight: spacing.sm,
  },
  text: {
    ...typography.body,
    color: colors.textPrimary,
    flex: 1,
  },
});
