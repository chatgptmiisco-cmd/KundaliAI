import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import { useTranslation } from 'react-i18next';
import DailyReadingSections from '../components/DailyReadingSections';
import ErrorState from '../components/ErrorState';
import LoadingState from '../components/LoadingState';
import { getDailyReading } from '../api/client';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useUserStore } from '../store/useUserStore';
import { DailyReading } from '../types/kundali';
import { spacing } from '../theme/theme';

export default function HoroscopeDetailScreen() {
  const { t } = useTranslation();
  const language = toContentLanguage(useUserStore((s) => s.language));

  const [reading, setReading] = useState<DailyReading | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = () => {
    setLoading(true);
    setError(false);
    getDailyReading(language)
      .then((data) => setReading(data))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language]);

  if (loading) {
    return <LoadingState message={t('horoscope.loadingMessage')} />;
  }

  if (error || !reading) {
    return (
      <ErrorState title={t('kundali.errorTitle')} message={t('horoscope.errorMessage')} onRetry={load} />
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <DailyReadingSections reading={reading} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
});
