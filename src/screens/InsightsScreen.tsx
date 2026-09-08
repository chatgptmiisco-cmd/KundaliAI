import { Ionicons } from '@expo/vector-icons';
import React, { useEffect } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import Card from '../components/Card';
import { useInsightsStore } from '../store/useInsightsStore';
import { InsightTone } from '../types/kundali';
import { colors, radius, spacing, typography } from '../theme/theme';

const TONE_STYLES: Record<InsightTone, { bg: string; fg: string; icon: keyof typeof Ionicons.glyphMap }> = {
  good: { bg: colors.successLight, fg: colors.success, icon: 'checkmark-circle' },
  average: { bg: colors.primaryLight, fg: colors.primary, icon: 'remove-circle-outline' },
  watch: { bg: colors.accentLight, fg: colors.accentDark, icon: 'eye-outline' },
};

export default function InsightsScreen() {
  const { t } = useTranslation();
  const insights = useInsightsStore((s) => s.insights);
  const markAllRead = useInsightsStore((s) => s.markAllRead);

  useEffect(() => {
    markAllRead();
  }, []);

  if (insights.length === 0) {
    return (
      <View style={styles.empty}>
        <Ionicons name="sparkles-outline" size={32} color={colors.textSecondary} />
        <Text style={styles.emptyText}>{t('insights.emptyState')}</Text>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      {insights.map((insight) => {
        const tone = TONE_STYLES[insight.tone];
        return (
          <Card key={insight.id}>
            <View style={styles.headerRow}>
              <Text style={styles.title}>{insight.title}</Text>
              <View style={[styles.tonePill, { backgroundColor: tone.bg }]}>
                <Ionicons name={tone.icon} size={14} color={tone.fg} />
                <Text style={[styles.tonePillText, { color: tone.fg }]}>
                  {t(`insights.tone${insight.tone === 'good' ? 'Good' : insight.tone === 'average' ? 'Average' : 'Watch'}`)}
                </Text>
              </View>
            </View>
            <Text style={styles.message}>{insight.message}</Text>
          </Card>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  empty: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.sm,
  },
  emptyText: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
  },
  headerRow: {
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
  tonePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  tonePillText: {
    ...typography.caption,
    fontSize: 12,
  },
  message: {
    ...typography.body,
    color: colors.textPrimary,
  },
});
