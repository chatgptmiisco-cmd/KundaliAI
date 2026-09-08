import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Linking, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { colors, spacing, typography } from '../theme/theme';
import PrimaryButton from './PrimaryButton';

interface Props {
  title: string;
  message: string;
  onRetry: () => void;
}

export default function ErrorState({ title, message, onRetry }: Props) {
  const { t } = useTranslation();
  return (
    <View style={styles.wrap} accessibilityRole="alert">
      <Ionicons name="cloud-offline-outline" size={40} color={colors.textSecondary} />
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
      <View style={styles.actions}>
        <PrimaryButton label={t('common.tryAgain')} onPress={onRetry} />
        <PrimaryButton
          label={t('common.contactSupport')}
          variant="outline"
          onPress={() => Linking.openURL('mailto:support@kundaliai.app')}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  title: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
    marginTop: spacing.md,
    textAlign: 'center',
  },
  message: {
    ...typography.body,
    color: colors.textSecondary,
    marginTop: spacing.sm,
    marginBottom: spacing.lg,
    textAlign: 'center',
  },
  actions: {
    width: '100%',
    gap: spacing.sm,
  },
});
