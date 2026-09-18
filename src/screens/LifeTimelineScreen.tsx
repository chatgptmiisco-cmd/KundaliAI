import React, { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { getLifeTimeline, LifeTimelineEntry } from '../api/client';
import GlassSurface from '../components/GlassSurface';
import { colors, radius, spacing, typography } from '../theme/theme';
import { showAlert } from '../utils/crossPlatformAlert';

/** Product spec §10 — Life Timeline: every meaningful event the app has
 * picked up from conversation, grouped by year, oldest first — so a later
 * conversation can genuinely reason "your situation today is different
 * from your 2024 situation because...". Read-only for now (no add/edit UI
 * yet — events are extracted from chat, not hand-entered here). */
export default function LifeTimelineScreen() {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<LifeTimelineEntry[] | null>(null);

  useEffect(() => {
    getLifeTimeline()
      .then(setEntries)
      .catch(() => showAlert(t('common.tryAgain'), t('lifeTimeline.loadError')));
  }, [t]);

  const byYear: Record<number, LifeTimelineEntry[]> = {};
  for (const e of entries ?? []) {
    (byYear[e.year] ??= []).push(e);
  }
  const years = Object.keys(byYear).map(Number).sort((a, b) => a - b);

  return (
    <ScrollView contentContainerStyle={styles.content}>
      {entries === null && <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.primary} />}

      {entries !== null && years.length === 0 && (
        <GlassSurface style={styles.emptyCard}>
          <Text style={styles.emptyText}>{t('lifeTimeline.empty')}</Text>
        </GlassSurface>
      )}

      {years.map((year) => (
        <View key={year} style={styles.yearBlock}>
          <Text style={styles.yearLabel}>{year}</Text>
          <GlassSurface style={styles.yearCard}>
            {byYear[year].map((e, i) => (
              <View key={e.id} style={[styles.eventRow, i > 0 && styles.eventRowDivider]}>
                <View style={styles.dot} />
                <Text style={styles.eventText}>{e.description}</Text>
              </View>
            ))}
          </GlassSurface>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  emptyCard: {
    padding: spacing.lg,
  },
  emptyText: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
  },
  yearBlock: {
    marginBottom: spacing.md,
  },
  yearLabel: {
    ...typography.title,
    color: colors.primary,
    marginBottom: spacing.xs,
  },
  yearCard: {
    padding: spacing.md,
  },
  eventRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  eventRowDivider: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.primary,
  },
  eventText: {
    ...typography.body,
    color: colors.textPrimary,
    flex: 1,
  },
});
