import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import Card from '../components/Card';
import PrimaryButton from '../components/PrimaryButton';
import { PASS_OPTIONS } from '../data/catalog';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useUserStore } from '../store/useUserStore';
import { colors, spacing, typography } from '../theme/theme';

export default function PassStoreScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const language = toContentLanguage(useUserStore((s) => s.language));

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.subtitle}>{t('passStore.subtitle')}</Text>

      {PASS_OPTIONS.map((pass) => (
        <Card key={pass.id}>
          <View style={styles.row}>
            <Ionicons name="diamond" size={28} color={colors.primary} />
            <View style={styles.info}>
              <Text style={styles.label}>{pass.durationLabel[language]}</Text>
              <Text style={styles.subLabel}>
                {pass.credits} {t('passStore.creditsSuffix')}
              </Text>
            </View>
            <Text style={styles.price}>₹{pass.priceInr}</Text>
          </View>
          <PrimaryButton
            label={t('passStore.buyButton')}
            onPress={() => navigation.navigate('Payment', { passId: pass.id })}
          />
        </Card>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  subtitle: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.md,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginBottom: spacing.md,
  },
  info: {
    flex: 1,
  },
  label: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
  },
  subLabel: {
    ...typography.body,
    color: colors.textSecondary,
  },
  price: {
    ...typography.title,
    color: colors.primary,
  },
});
