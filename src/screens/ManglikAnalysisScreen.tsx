import React, { useEffect } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import BulletList from '../components/BulletList';
import Card from '../components/Card';
import ErrorState from '../components/ErrorState';
import LoadingState from '../components/LoadingState';
import ManglikBadge from '../components/ManglikBadge';
import SpeakerButton from '../components/SpeakerButton';
import { trackEvent } from '../analytics/analytics';
import { buildRemedies } from '../data/remedies';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useKundaliStore } from '../store/useKundaliStore';
import { useUserStore } from '../store/useUserStore';
import { colors, spacing, typography } from '../theme/theme';

export default function ManglikAnalysisScreen() {
  const { t } = useTranslation();
  const language = toContentLanguage(useUserStore((s) => s.language));

  const manglik = useKundaliStore((s) => s.manglik[language]);
  const loading = useKundaliStore((s) => s.manglikLoading);
  const error = useKundaliStore((s) => s.manglikError);
  const fetchManglik = useKundaliStore((s) => s.fetchManglik);

  useEffect(() => {
    fetchManglik(language);
  }, [language]);

  useEffect(() => {
    if (manglik) {
      trackEvent('manglik_details_viewed', { language, source: 'manglik_screen' });
    }
  }, [manglik, language]);

  if (loading) {
    return <LoadingState message={t('kundali.preparingKundali')} />;
  }

  if (error || !manglik) {
    return (
      <ErrorState
        title={t('kundali.errorTitle')}
        message={t('kundali.errorMessage')}
        onRetry={() => fetchManglik(language)}
      />
    );
  }

  const voiceText = [
    manglik.summary,
    manglik.details.join(' '),
    manglik.cancellations.length > 0
      ? manglik.cancellations.join(' ')
      : t('manglik.noCancellations'),
    manglik.relationshipNote,
  ].join(' ');

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <ManglikBadge statusLine={manglik.summary} size="large" />

      <View style={styles.speakerRow}>
        <SpeakerButton
          label={t('common.listenToThisAnalysis')}
          title={t('manglik.screenTitle')}
          text={voiceText}
          analyticsSource="manglik"
        />
      </View>

      <Card>
        <Text style={styles.sectionTitle}>{t('manglik.explanationTitle')}</Text>
        <BulletList
          items={[
            `${t('manglik.marsHouseFromLagnaLabel')}: ${manglik.marsHouseFromLagna}`,
            `${t('manglik.marsHouseFromMoonLabel')}: ${manglik.marsHouseFromMoon}`,
            ...manglik.details,
          ]}
        />
      </Card>

      <Card>
        <Text style={styles.sectionTitle}>{t('manglik.cancellationsTitle')}</Text>
        <BulletList
          items={
            manglik.cancellations.length > 0
              ? manglik.cancellations
              : [t('manglik.noCancellations')]
          }
        />
      </Card>

      <Card>
        <Text style={styles.sectionTitle}>{t('manglik.relationshipImplicationsTitle')}</Text>
        <Text style={styles.body}>{manglik.relationshipNote}</Text>
      </Card>

      <Card>
        <Text style={styles.sectionTitle}>{t('manglik.remediesTitle')}</Text>
        <BulletList items={buildRemedies(language).map((r) => r.text)} />
        <Text style={styles.disclaimer}>{t('manglik.remediesDisclaimer')}</Text>
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  speakerRow: {
    alignItems: 'flex-start',
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  sectionTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  body: {
    ...typography.body,
    color: colors.textPrimary,
  },
  disclaimer: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: spacing.sm,
  },
});
