import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';
import React, { useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import Card from '../components/Card';
import PrimaryButton from '../components/PrimaryButton';
import { PASS_OPTIONS } from '../data/catalog';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useUserStore } from '../store/useUserStore';
import { colors, radius, spacing, typography } from '../theme/theme';

export default function PaymentScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const passId: string = route.params?.passId;
  const pass = PASS_OPTIONS.find((p) => p.id === passId) ?? PASS_OPTIONS[0];
  const language = toContentLanguage(useUserStore((s) => s.language));
  const addCredits = useUserStore((s) => s.addCredits);

  const [status, setStatus] = useState<'idle' | 'processing' | 'success'>('idle');

  const handlePay = () => {
    setStatus('processing');
    setTimeout(() => {
      addCredits(pass.credits);
      setStatus('success');
    }, 1400);
  };

  const handleDone = () => {
    if (typeof navigation.pop === 'function') {
      navigation.pop(2);
    } else {
      navigation.goBack();
    }
  };

  return (
    <View style={styles.content}>
      <View style={styles.demoNotice}>
        <Ionicons name="information-circle-outline" size={18} color={colors.premium} />
        <Text style={styles.demoNoticeText}>{t('payment.demoNotice')}</Text>
      </View>

      <Card>
        <Text style={styles.label}>{pass.durationLabel[language]}</Text>
        <Text style={styles.subLabel}>
          {pass.credits} {t('passStore.creditsSuffix')}
        </Text>
        <Text style={styles.price}>₹{pass.priceInr}</Text>
      </Card>

      {status !== 'success' && (
        <PrimaryButton
          label={t('payment.payNow')}
          onPress={handlePay}
          loading={status === 'processing'}
        />
      )}

      {status === 'processing' && (
        <View style={styles.processingRow}>
          <ActivityIndicator color={colors.primary} />
          <Text style={styles.processingText}>{t('payment.processing')}</Text>
        </View>
      )}

      {status === 'success' && (
        <Card style={styles.successCard}>
          <Ionicons name="checkmark-circle" size={36} color={colors.success} />
          <Text style={styles.successTitle}>{t('payment.successTitle')}</Text>
          <Text style={styles.successMessage}>
            {t('payment.successMessage', { count: pass.credits })}
          </Text>
          <PrimaryButton label={t('payment.doneButton')} onPress={handleDone} />
        </Card>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  content: {
    flex: 1,
    padding: spacing.md,
    backgroundColor: colors.background,
    gap: spacing.md,
  },
  demoNotice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.premiumLight,
    borderRadius: radius.md,
    padding: spacing.sm,
  },
  demoNoticeText: {
    ...typography.caption,
    color: colors.premium,
    flexShrink: 1,
  },
  label: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
  },
  subLabel: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  price: {
    ...typography.display,
    color: colors.primary,
  },
  processingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  processingText: {
    ...typography.body,
    color: colors.textSecondary,
  },
  successCard: {
    alignItems: 'center',
    gap: spacing.sm,
  },
  successTitle: {
    ...typography.title,
    color: colors.textPrimary,
  },
  successMessage: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.sm,
  },
});
