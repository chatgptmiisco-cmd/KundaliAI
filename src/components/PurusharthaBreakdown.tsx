import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import Card from './Card';
import DefinitionTooltip from './DefinitionTooltip';
import { PURUSHARTHA_HOUSES, PURUSHARTHA_ORDER, PurusharthaKey } from '../constants/purusharthas';
import { BirthChart, PlanetKey } from '../types/kundali';
import { colors, radius, spacing, typography } from '../theme/theme';

interface Props {
  chart: BirthChart;
  language: 'en' | 'hi';
}

type Mode = 'direct' | 'deepDive';

const _TOOLTIP_TERMS = ['exalted', 'debilitated', 'ownSign', 'retrograde', 'combust', 'nakshatra', 'pada'] as const;

export default function PurusharthaBreakdown({ chart, language }: Props) {
  const { t } = useTranslation();
  const hi = language === 'hi';
  const [selected, setSelected] = useState<PurusharthaKey>('dharma');
  const [mode, setMode] = useState<Mode>('direct');

  const houses = PURUSHARTHA_HOUSES[selected];
  const houseEntries = houses
    .map((h) => chart.houseBreakdown.find((entry) => entry.house === h))
    .filter((entry): entry is NonNullable<typeof entry> => !!entry);

  return (
    <Card>
      <Text style={styles.title}>{t('charts.purusharthas.title')}</Text>
      <Text style={styles.subtitle}>{t('charts.purusharthas.subtitle')}</Text>

      <View style={styles.tabs}>
        {PURUSHARTHA_ORDER.map((key) => {
          const active = key === selected;
          return (
            <Pressable
              key={key}
              onPress={() => setSelected(key)}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              style={[styles.tab, active && styles.tabActive]}
            >
              <Text style={[styles.tabText, active && styles.tabTextActive]}>
                {t(`charts.purusharthas.${key}Title`)}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={styles.categorySubtitle}>{t(`charts.purusharthas.${selected}Subtitle`)}</Text>

      <View style={styles.modeToggle}>
        <Pressable
          onPress={() => setMode('direct')}
          style={[styles.modeButton, mode === 'direct' && styles.modeButtonActive]}
        >
          <Text style={[styles.modeText, mode === 'direct' && styles.modeTextActive]}>
            {t('charts.purusharthas.directMode')}
          </Text>
        </Pressable>
        <Pressable
          onPress={() => setMode('deepDive')}
          style={[styles.modeButton, mode === 'deepDive' && styles.modeButtonActive]}
        >
          <Text style={[styles.modeText, mode === 'deepDive' && styles.modeTextActive]}>
            {t('charts.purusharthas.deepDiveMode')}
          </Text>
        </Pressable>
      </View>

      {mode === 'deepDive' && (
        <View style={styles.glossaryRow}>
          {_TOOLTIP_TERMS.map((key) => (
            <DefinitionTooltip
              key={key}
              term={t(`charts.tooltip.${key}Term`)}
              definition={t(`charts.tooltip.${key}Definition`)}
            >
              {t(`charts.tooltip.${key}Term`)}
            </DefinitionTooltip>
          ))}
        </View>
      )}

      {houseEntries.map((entry) => (
        <View key={entry.house} style={styles.houseBlock}>
          <Text style={styles.houseHeading}>
            {t('kundali.houseLabel')} {entry.house} — {hi ? entry.signNameHi : entry.signNameEn}
          </Text>
          {mode === 'direct' ? (
            <Text style={styles.explanation}>{hi ? entry.explanationHi : entry.explanationEn}</Text>
          ) : (
            <View>
              {entry.planets.length === 0 && (
                <Text style={styles.explanation}>{hi ? entry.explanationHi : entry.explanationEn}</Text>
              )}
              {entry.planets.map((planetKey: PlanetKey) => {
                const detail = chart.planetDetails[planetKey];
                if (!detail) return null;
                const dignityLabel = detail.dignity ? t(`kundali.dignity.${detail.dignity}`) : null;
                return (
                  <Text key={planetKey} style={styles.deepDiveLine}>
                    {t('charts.purusharthas.deepDivePlanetLine', {
                      planet: planetKey,
                      degree: detail.degreeDisplay ?? '—',
                      nakshatra: detail.nakshatraName ?? '—',
                      pada: detail.nakshatraPada ?? '—',
                      dignity: dignityLabel ?? '—',
                    })}
                    {detail.retrograde ? ` · ${t('charts.tooltip.retrogradeTerm')}` : ''}
                    {detail.combust ? ` · ${t('charts.tooltip.combustTerm')}` : ''}
                  </Text>
                );
              })}
            </View>
          )}
        </View>
      ))}
    </Card>
  );
}

const styles = StyleSheet.create({
  title: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
  },
  subtitle: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: spacing.xs,
    marginBottom: spacing.md,
  },
  tabs: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.md,
    padding: spacing.xs,
  },
  tab: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
    paddingHorizontal: spacing.xs,
  },
  tabActive: {
    backgroundColor: colors.primary,
  },
  tabText: {
    ...typography.caption,
    color: colors.textSecondary,
    textAlign: 'center',
  },
  tabTextActive: {
    color: colors.textOnPrimary, // active tab bg is now light gold, textInverse would wash out
  },
  categorySubtitle: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: spacing.sm,
  },
  modeToggle: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  modeButton: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
  },
  modeButtonActive: {
    backgroundColor: colors.primaryLight,
    borderColor: colors.primary,
  },
  modeText: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  modeTextActive: {
    color: colors.textOnPrimary, // sits on primaryLight bg, primary text is now too light too
  },
  glossaryRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginTop: spacing.md,
    paddingBottom: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  houseBlock: {
    marginTop: spacing.md,
  },
  houseHeading: {
    ...typography.bodyBold,
    color: colors.textPrimary,
  },
  explanation: {
    ...typography.body,
    color: colors.textSecondary,
    marginTop: spacing.xs,
  },
  deepDiveLine: {
    ...typography.body,
    color: colors.textSecondary,
    marginTop: spacing.xs,
  },
});
