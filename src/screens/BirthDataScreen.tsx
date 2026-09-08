import { useNavigation } from '@react-navigation/native';
import React, { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import BirthDataFields from '../components/BirthDataFields';
import PrimaryButton from '../components/PrimaryButton';
import { useUserStore } from '../store/useUserStore';
import { BirthData } from '../types/kundali';
import { colors, spacing, typography } from '../theme/theme';

export default function BirthDataScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const setBirthData = useUserStore((s) => s.setBirthData);
  const [data, setData] = useState<BirthData>({
    name: '',
    dateOfBirth: '',
    timeOfBirth: '',
    placeOfBirth: '',
  });
  const [submitting, setSubmitting] = useState(false);

  const canSubmit =
    data.name.trim() && data.dateOfBirth.trim() && data.timeOfBirth.trim() && data.placeOfBirth.trim();

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await setBirthData(data);
      navigation.navigate('AiProcessing');
    } catch (err: any) {
      Alert.alert(t('common.tryAgain'), err?.message ?? String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.title}>{t('onboarding.birthDataTitle')}</Text>
      <Text style={styles.subtitle}>{t('onboarding.birthDataSubtitle')}</Text>

      <View style={{ height: spacing.lg }} />
      <BirthDataFields value={data} onChange={setData} />

      <View style={{ height: spacing.md }} />
      <PrimaryButton
        label={t('onboarding.generateKundali')}
        disabled={!canSubmit || submitting}
        loading={submitting}
        onPress={handleSubmit}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  title: {
    ...typography.title,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  subtitle: {
    ...typography.body,
    color: colors.textSecondary,
  },
});
