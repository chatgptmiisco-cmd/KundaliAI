import { useNavigation } from '@react-navigation/native';
import React, { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import BirthDataFields from '../components/BirthDataFields';
import CosmicBackground from '../components/CosmicBackground';
import GlassSurface from '../components/GlassSurface';
import PrimaryButton from '../components/PrimaryButton';
import { useUserStore } from '../store/useUserStore';
import { BirthData } from '../types/kundali';
import { colors, spacing, typography } from '../theme/theme';
import { showAlert } from '../utils/crossPlatformAlert';

export default function BirthDataScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const setBirthData = useUserStore((s) => s.setBirthData);
  // Name is already known once it's come from signup (see
  // useUserStore.hydrateAccountName) — starting from the store's current
  // draft instead of a blank object is what lets this screen skip asking
  // for it again below, while a name-less arrival (e.g. a future entry
  // point that never collected one) still falls back to asking normally.
  const existingBirthData = useUserStore((s) => s.birthData);
  const [data, setData] = useState<BirthData>({
    name: existingBirthData.name ?? '',
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
      navigation.navigate('TopicSelection');
    } catch (err: any) {
      showAlert(t('common.tryAgain'), err?.message ?? String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <CosmicBackground>
      <ScrollView contentContainerStyle={styles.content}>
        <GlassSurface style={styles.headerCard}>
          <Text style={styles.title}>{t('onboarding.birthDataTitle')}</Text>
          <Text style={styles.subtitle}>{t('onboarding.birthDataSubtitle')}</Text>
        </GlassSurface>

        <GlassSurface style={styles.fieldsCard}>
          <BirthDataFields value={data} onChange={setData} hideNameField={!!data.name.trim()} />
        </GlassSurface>

        <PrimaryButton
          label={t('onboarding.generateKundali')}
          disabled={!canSubmit || submitting}
          loading={submitting}
          onPress={handleSubmit}
        />
      </ScrollView>
    </CosmicBackground>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
    gap: spacing.md,
  },
  headerCard: {
    padding: spacing.md,
  },
  fieldsCard: {
    padding: spacing.md,
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
