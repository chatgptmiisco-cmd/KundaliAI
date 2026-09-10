import React, { useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, elevation, radius, spacing, typography } from '../theme/theme';

interface Props {
  term: string;
  definition: string;
  children: React.ReactNode;
}

/** Wraps a jargon word (Exalted, Retrograde, Nakshatra, Pada, ...) so tapping
 * it shows a small plain-language definition instead of leaving the reader to
 * guess — the "micro-lesson" mechanism used inside Deep Dive mode. */
export default function DefinitionTooltip({ term, definition, children }: Props) {
  const [visible, setVisible] = useState(false);

  return (
    <>
      <Pressable onPress={() => setVisible(true)} accessibilityRole="button" accessibilityLabel={term}>
        <Text style={styles.trigger}>{children}</Text>
      </Pressable>
      <Modal transparent visible={visible} animationType="fade" onRequestClose={() => setVisible(false)}>
        <Pressable style={styles.backdrop} onPress={() => setVisible(false)}>
          <Pressable style={styles.card}>
            <Text style={styles.term}>{term}</Text>
            <Text style={styles.definition}>{definition}</Text>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  trigger: {
    textDecorationLine: 'underline',
    textDecorationStyle: 'dotted',
    color: colors.primary,
  },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(43,36,28,0.4)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.lg,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    maxWidth: 340,
    ...elevation.raised,
  },
  term: {
    ...typography.bodyBold,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  definition: {
    ...typography.body,
    color: colors.textSecondary,
  },
});
