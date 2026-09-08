import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { colors, radius, spacing, typography } from '../theme/theme';
import PrimaryButton from './PrimaryButton';

interface Props {
  visible: boolean;
  onClose: () => void;
  onUpgrade: () => void;
  message?: string;
  icon?: keyof typeof Ionicons.glyphMap;
}

export default function PremiumModal({
  visible,
  onClose,
  onUpgrade,
  message,
  icon = 'mic',
}: Props) {
  const { t } = useTranslation();
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <View style={styles.iconWrap}>
            <Ionicons name={icon} size={28} color={colors.premium} />
          </View>
          <Text style={styles.title}>{t('common.premiumFeature')}</Text>
          <Text style={styles.body}>{message ?? t('common.premiumTooltip')}</Text>
          <PrimaryButton label={t('common.upgrade')} onPress={onUpgrade} />
          <Pressable
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel={t('common.cancel')}
            style={styles.cancelBtn}
          >
            <Text style={styles.cancelText}>{t('common.cancel')}</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(43,36,28,0.45)',
    justifyContent: 'center',
    padding: spacing.lg,
  },
  sheet: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    alignItems: 'center',
  },
  iconWrap: {
    width: 56,
    height: 56,
    borderRadius: radius.pill,
    backgroundColor: colors.premiumLight,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  title: {
    ...typography.title,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
    textAlign: 'center',
  },
  body: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.lg,
  },
  cancelBtn: {
    marginTop: spacing.md,
    minHeight: 44,
    justifyContent: 'center',
  },
  cancelText: {
    ...typography.bodyBold,
    color: colors.textSecondary,
  },
});
