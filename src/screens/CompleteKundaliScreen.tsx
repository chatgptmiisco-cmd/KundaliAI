import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import React, { useEffect, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import BulletList from '../components/BulletList';
import Card from '../components/Card';
import ErrorState from '../components/ErrorState';
import LanguageToggle from '../components/LanguageToggle';
import LoadingState from '../components/LoadingState';
import ManglikBadge from '../components/ManglikBadge';
import PlanetPositionsTable from '../components/PlanetPositionsTable';
import PremiumModal from '../components/PremiumModal';
import PrimaryButton from '../components/PrimaryButton';
import SectionHeader from '../components/SectionHeader';
import SouthIndianChart from '../components/SouthIndianChart';
import SpeakerButton from '../components/SpeakerButton';
import { trackEvent } from '../analytics/analytics';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useKundaliStore } from '../store/useKundaliStore';
import { useUserStore } from '../store/useUserStore';
import { colors, fontFamily, radius, spacing, typography } from '../theme/theme';

export default function CompleteKundaliScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const language = toContentLanguage(useUserStore((s) => s.language));
  const isPremium = useUserStore((s) => s.isPremium);

  const complete = useKundaliStore((s) => s.complete[language]);
  const loading = useKundaliStore((s) => s.completeLoading);
  const error = useKundaliStore((s) => s.completeError);
  const fetchComplete = useKundaliStore((s) => s.fetchComplete);

  // The chart diagram itself (D1) — shown above the narrative explanation
  // below so people see the actual kundali before reading what it means.
  const d1Chart = useKundaliStore((s) => s.charts.D1?.[language]);
  const fetchChart = useKundaliStore((s) => s.fetchChart);

  const [saved, setSaved] = useState(false);
  const [pdfModalVisible, setPdfModalVisible] = useState(false);

  useEffect(() => {
    fetchComplete(language);
    fetchChart('D1', language);
  }, [language]);

  useEffect(() => {
    if (complete) {
      trackEvent('complete_kundali_viewed', { language });
      trackEvent('manglik_details_viewed', { language, source: 'kundali_screen' });
    }
  }, [complete, language]);

  if (loading) {
    return <LoadingState message={t('kundali.preparingKundali')} />;
  }

  if (error || !complete) {
    return (
      <ErrorState
        title={t('kundali.errorTitle')}
        message={t('kundali.errorMessage')}
        onRetry={() => fetchComplete(language)}
      />
    );
  }

  const fullExplanationText = [
    complete.basicDetails.map((d) => `${d.label}: ${d.value}`).join('. '),
    ...complete.sections.map((s) => `${s.title}. ${s.summary}`),
    complete.manglik.summary,
    complete.brutalTruth,
  ].join('. ');

  const handleSave = () => {
    setSaved(true);
    Alert.alert(t('common.readLater'), t('kundali.savedConfirmation'));
  };

  const handleDownloadPdf = () => {
    if (!isPremium) {
      setPdfModalVisible(true);
      return;
    }
    Alert.alert(t('common.downloadPdf'), t('kundali.pdfPreparingMessage'));
  };

  return (
    <View style={styles.screen}>
      <View style={styles.topBar}>
        <LanguageToggle />
        <SpeakerButton
          label={t('common.listenToFullExplanation')}
          title={t('kundali.screenTitle')}
          text={fullExplanationText}
          analyticsSource="kundali"
        />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
      {d1Chart && (
        <Card style={styles.chartCard}>
          <SectionHeader title={t('kundali.yourKundaliTitle')} />
          <View style={styles.chartWrap}>
            <SouthIndianChart chart={d1Chart} language={language} size={280} />
          </View>
        </Card>
      )}

      <Card>
        <SectionHeader title={t('kundali.basicDetailsTitle')} />
        <BulletList items={complete.basicDetails.map((d) => `${d.label}: ${d.value}`)} />
      </Card>

      {d1Chart && (
        <Card>
          <SectionHeader title={t('kundali.planetaryPositionsTitle')} />
          <PlanetPositionsTable chart={d1Chart} language={language} />
        </Card>
      )}

      {complete.sections.map((section) => (
        <Card key={section.id}>
          <SectionHeader
            title={section.title}
            voiceText={`${section.title}. ${section.summary} ${section.keyPoints.join('. ')}`}
            voiceLabel={t('common.listenToThisSection')}
            analyticsSource="kundali"
          />
          <Text style={styles.summary}>{section.summary}</Text>
          {section.keyPoints.length > 0 && (
            <>
              <Text style={styles.keyPointsLabel}>{t('kundali.keyPointsLabel')}</Text>
              <BulletList items={section.keyPoints} />
            </>
          )}

          {section.id === 'relationshipsMarriage' && (
            <View style={styles.manglikSubsection}>
              <SectionHeader
                title={t('kundali.manglikStatusSectionTitle')}
                voiceText={`${complete.manglik.summary} ${complete.manglik.details.join(' ')} ${complete.manglik.relationshipNote}`}
                voiceLabel={t('common.listenToThisSection')}
                analyticsSource="manglik"
              />
              <ManglikBadge statusLine={complete.manglik.summary} size="medium" />
              <View style={{ height: spacing.sm }} />
              <BulletList items={complete.manglik.details} />
              <PrimaryButton
                label={t('kundali.viewFullManglikAnalysis')}
                variant="outline"
                onPress={() => navigation.navigate('ManglikAnalysis')}
              />
            </View>
          )}
        </Card>
      ))}

      <Card style={styles.brutalTruthCard}>
        <Text style={styles.brutalTruthLabel}>{t('kundali.brutalTruthLabel')}</Text>
        <Text style={styles.brutalTruthText}>{complete.brutalTruth}</Text>
      </Card>

      <View style={styles.footerActions}>
        <PrimaryButton
          label={t('common.readLater')}
          variant="outline"
          icon={
            <Ionicons
              name={saved ? 'bookmark' : 'bookmark-outline'}
              size={20}
              color={colors.primary}
            />
          }
          onPress={handleSave}
        />
        <PrimaryButton
          label={t('common.downloadPdf')}
          variant="secondary"
          icon={<Ionicons name="download-outline" size={20} color={colors.textInverse} />}
          onPress={handleDownloadPdf}
        />
      </View>

      <PremiumModal
        visible={pdfModalVisible}
        onClose={() => setPdfModalVisible(false)}
        onUpgrade={() => {
          setPdfModalVisible(false);
          navigation.navigate('UpgradePlans');
        }}
        message={t('common.premiumTooltipGeneric') as string}
        icon="document-text-outline"
      />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  chartCard: {
    alignItems: 'center',
  },
  chartWrap: {
    paddingVertical: spacing.sm,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  summary: {
    ...typography.body,
    color: colors.textPrimary,
  },
  keyPointsLabel: {
    ...typography.bodyBold,
    color: colors.textSecondary,
    marginTop: spacing.md,
  },
  manglikSubsection: {
    marginTop: spacing.lg,
    paddingTop: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  brutalTruthCard: {
    backgroundColor: colors.primaryLight,
    borderColor: colors.primary,
  },
  brutalTruthLabel: {
    ...typography.caption,
    color: colors.primaryDark,
    fontFamily: fontFamily.bold,
    marginBottom: spacing.xs,
  },
  brutalTruthText: {
    ...typography.bodyBold,
    color: colors.primaryDark,
  },
  footerActions: {
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
});
