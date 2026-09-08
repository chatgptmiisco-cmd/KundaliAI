import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { colors, spacing, typography } from '../theme/theme';
import SpeakerButton from './SpeakerButton';

interface Props {
  title: string;
  voiceText?: string;
  voiceLabel?: string;
  analyticsSource?: 'kundali' | 'manglik';
}

export default function SectionHeader({ title, voiceText, voiceLabel, analyticsSource }: Props) {
  return (
    <View style={styles.row}>
      <Text style={styles.title}>{title}</Text>
      {voiceText && voiceLabel && analyticsSource && (
        <SpeakerButton
          label={voiceLabel}
          title={title}
          text={voiceText}
          analyticsSource={analyticsSource}
          compact
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
    gap: spacing.sm,
  },
  title: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
    flexShrink: 1,
  },
});
