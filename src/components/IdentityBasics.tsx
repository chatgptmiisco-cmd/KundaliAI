import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import Card from './Card';
import { Identity } from '../types/kundali';
import { colors, fontFamily, radius, spacing, typography } from '../theme/theme';

interface Props {
  identity: Identity;
  language: 'en' | 'hi';
}

// Local to this one visualization — a small, warm-palette-consistent swatch
// per classical element, not a global theme token (nothing else in the app
// needs an air/water/fire/earth color).
const ELEMENT_COLOR_EN: Record<string, string> = {
  Fire: colors.accent,
  Earth: '#6B8E4E',
  Air: '#7C8FBE',
  Water: '#4D7C8A',
};
// Same 4 swatches, keyed by the Hindi element label so the bar/legend stay
// correctly colored regardless of which language is displayed.
const ELEMENT_COLOR_HI: Record<string, string> = {
  'अग्नि': colors.accent,
  'पृथ्वी': '#6B8E4E',
  'वायु': '#7C8FBE',
  'जल': '#4D7C8A',
};

export default function IdentityBasics({ identity, language }: Props) {
  const { t } = useTranslation();
  const hi = language === 'hi';

  const bigThree = [
    {
      label: t('charts.identity.lagnaLabel'),
      value: hi ? identity.lagna.signHi : identity.lagna.signEn,
      realEffect: hi ? identity.lagna.realEffectHi : identity.lagna.realEffectEn,
      meaning: hi ? identity.lagna.meaningHi : identity.lagna.meaningEn,
      icon: 'body-outline' as const,
      accent: colors.primary,
      accentLight: colors.primaryLight,
    },
    {
      label: t('charts.identity.moonLabel'),
      value: hi ? identity.moonSign.signHi : identity.moonSign.signEn,
      realEffect: hi ? identity.moonSign.realEffectHi : identity.moonSign.realEffectEn,
      meaning: hi ? identity.moonSign.meaningHi : identity.moonSign.meaningEn,
      icon: 'moon-outline' as const,
      accent: '#4D7C8A',
      accentLight: '#E3EEF0',
    },
    {
      label: t('charts.identity.sunLabel'),
      value: hi ? identity.sunSign.signHi : identity.sunSign.signEn,
      realEffect: hi ? identity.sunSign.realEffectHi : identity.sunSign.realEffectEn,
      meaning: hi ? identity.sunSign.meaningHi : identity.sunSign.meaningEn,
      icon: 'sunny-outline' as const,
      accent: colors.accentDark,
      accentLight: colors.accentLight,
    },
  ];

  const elementCounts: Record<string, number> = {};
  const elementColorMap = hi ? ELEMENT_COLOR_HI : ELEMENT_COLOR_EN;
  for (const p of identity.elementModality) {
    const el = hi ? p.elementHi : p.elementEn;
    elementCounts[el] = (elementCounts[el] ?? 0) + 1;
  }
  const total = identity.elementModality.length;

  return (
    <View>
      {bigThree.map((item) => (
        <Card key={item.label} style={{ ...styles.bigThreeCard, borderLeftColor: item.accent }}>
          <View style={styles.bigThreeHeaderRow}>
            <View style={[styles.iconBadge, { backgroundColor: item.accentLight }]}>
              <Ionicons name={item.icon} size={20} color={item.accent} />
            </View>
            <View style={styles.bigThreeHeaderText}>
              <Text style={styles.bigThreeLabel}>{item.label}</Text>
              <Text style={[styles.bigThreeValue, { color: item.accent }]}>{item.value}</Text>
            </View>
          </View>
          {/* Led with: the real, per-chart consequence of this placement. */}
          <Text style={styles.realEffect}>{item.realEffect}</Text>
          {/* Secondary: the fixed classical definition of what this point represents. */}
          <Text style={styles.bigThreeMeaning}>{item.meaning}</Text>
        </Card>
      ))}

      <Card>
        <Text style={styles.nakshatraLabel}>{t('charts.identity.nakshatraLabel')}</Text>
        <Text style={styles.nakshatraName}>{hi ? identity.nakshatra.nameHi : identity.nakshatra.nameEn}</Text>
        <Text style={styles.nakshatraDetail}>{t('charts.identity.nakshatraPada', { pada: identity.nakshatra.pada })}</Text>
        <Text style={styles.nakshatraDetail}>
          {t('charts.identity.nakshatraLord', { lord: hi ? identity.nakshatra.lordHi : identity.nakshatra.lordEn })}
        </Text>
        <Text style={styles.nakshatraDetail}>
          {t('charts.identity.nakshatraSymbol', { symbol: hi ? identity.nakshatra.symbolHi : identity.nakshatra.symbolEn })}
        </Text>
        <Text style={styles.nakshatraMeaning}>{hi ? identity.nakshatra.meaningHi : identity.nakshatra.meaningEn}</Text>
      </Card>

      <Card>
        <Text style={styles.elementTitle}>{t('charts.identity.elementModalityTitle')}</Text>
        <Text style={styles.elementSubtitle}>{t('charts.identity.elementModalitySubtitle')}</Text>
        <View style={styles.bar}>
          {Object.entries(elementCounts).map(([element, count]) => (
            <View
              key={element}
              style={{
                flex: count,
                backgroundColor: elementColorMap[element] ?? colors.disabled,
              }}
            />
          ))}
        </View>
        <View style={styles.legendRow}>
          {Object.entries(elementCounts).map(([element, count]) => (
            <View key={element} style={styles.legendItem}>
              <View style={[styles.legendSwatch, { backgroundColor: elementColorMap[element] ?? colors.disabled }]} />
              <Text style={styles.legendText}>
                {element} · {count}/{total}
              </Text>
            </View>
          ))}
        </View>
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  bigThreeCard: {
    borderLeftWidth: 4,
  },
  bigThreeHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  iconBadge: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bigThreeHeaderText: {
    flex: 1,
  },
  bigThreeLabel: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  bigThreeValue: {
    ...typography.title,
    fontFamily: fontFamily.displayBold,
  },
  realEffect: {
    ...typography.body,
    color: colors.textPrimary,
    marginTop: spacing.sm,
  },
  bigThreeMeaning: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: spacing.sm,
    fontStyle: 'italic',
  },
  nakshatraLabel: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  nakshatraName: {
    ...typography.title,
    color: colors.primary,
    marginTop: spacing.xs,
  },
  nakshatraDetail: {
    ...typography.body,
    color: colors.textPrimary,
    marginTop: spacing.xs,
  },
  nakshatraMeaning: {
    ...typography.body,
    color: colors.textSecondary,
    marginTop: spacing.sm,
    fontStyle: 'italic',
  },
  elementTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
  },
  elementSubtitle: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: spacing.xs,
    marginBottom: spacing.md,
  },
  bar: {
    flexDirection: 'row',
    height: 24,
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  legendRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginTop: spacing.md,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  legendSwatch: {
    width: 12,
    height: 12,
    borderRadius: 3,
  },
  legendText: {
    ...typography.caption,
    color: colors.textSecondary,
  },
});
