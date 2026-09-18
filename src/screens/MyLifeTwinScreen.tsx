import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { correctLifeContextFact, deleteLifeContextFact, getMyLifeTwin, LifeContextFact, MyLifeTwin } from '../api/client';
import GlassSurface from '../components/GlassSurface';
import { colors, radius, spacing, typography } from '../theme/theme';
import { showAlert } from '../utils/crossPlatformAlert';

// Domain display order — identity/career/business/money first (the things
// people check on most), preferences last (usually the thinnest section).
const DOMAIN_ORDER = ['identity', 'career', 'business', 'money', 'relationships', 'family', 'goals', 'preferences'];

/** Product spec §14-15 — "My Life Twin": what the app actually remembers,
 * shown as real cards (not a database dump), with the user able to correct
 * or remove anything. "The Life Twin belongs to the user" — every fact
 * here came from something they actually said, and every one of them can
 * be taken back out just as easily. */
export default function MyLifeTwinScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const [data, setData] = useState<MyLifeTwin | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    getMyLifeTwin()
      .then(setData)
      .catch(() => showAlert(t('common.tryAgain'), t('lifeTwin.loadError')))
      .finally(() => setLoading(false));
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = (fact: LifeContextFact) => {
    showAlert(t('lifeTwin.deleteConfirmTitle'), t('lifeTwin.deleteConfirmMessage', { value: fact.value }), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('common.delete'),
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteLifeContextFact(fact.id);
            load();
          } catch (err: any) {
            showAlert(t('common.tryAgain'), err?.message ?? String(err));
          }
        },
      },
    ]);
  };

  const startEdit = (fact: LifeContextFact) => {
    setEditingId(fact.id);
    setDraft(fact.value);
  };

  const saveEdit = async (fact: LifeContextFact) => {
    const value = draft.trim();
    setEditingId(null);
    if (!value || value === fact.value) return;
    try {
      await correctLifeContextFact(fact.id, value);
      load();
    } catch (err: any) {
      showAlert(t('common.tryAgain'), err?.message ?? String(err));
    }
  };

  const domains = data ? Object.keys(data.facts).sort((a, b) => {
    const ia = DOMAIN_ORDER.indexOf(a);
    const ib = DOMAIN_ORDER.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  }) : [];

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.subtitle}>{t('lifeTwin.subtitle')}</Text>

      <Pressable
        onPress={() => navigation.navigate('LifeTimeline')}
        style={({ pressed }) => [styles.timelineLink, pressed && styles.pressedDim]}
      >
        <Ionicons name="time-outline" size={20} color={colors.primary} />
        <Text style={styles.timelineLinkText}>{t('lifeTwin.viewTimeline')}</Text>
        <Ionicons name="chevron-forward" size={18} color={colors.textSecondary} />
      </Pressable>

      {loading && <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.primary} />}

      {!loading && data && domains.length === 0 && data.decisions.length === 0 && (
        <GlassSurface style={styles.card}>
          <Text style={styles.emptyText}>{t('lifeTwin.empty')}</Text>
        </GlassSurface>
      )}

      {!loading && data?.decisions.map((d) => (
        <GlassSurface key={`decision-${d.id}`} style={styles.card}>
          <Text style={styles.domainTitle}>
            {t(`lifeTwin.decisionType.${d.decisionType}`, d.decisionType)}
          </Text>
          <Text style={styles.decisionStatus}>{t(`lifeTwin.decisionStatus.${d.status}`)}</Text>
          {!!d.context && <Text style={styles.factValue}>{d.context}</Text>}
          {!!d.outcome && (
            <Text style={styles.outcomeText}>{t('lifeTwin.outcomeLabel')}: {d.outcome}</Text>
          )}
        </GlassSurface>
      ))}

      {!loading && domains.map((domain) => (
        <GlassSurface key={domain} style={styles.card}>
          <Text style={styles.domainTitle}>{t(`lifeTwin.domain.${domain}`, domain)}</Text>
          {data!.facts[domain].map((fact) => (
            <View key={fact.id} style={styles.factRow}>
              {editingId === fact.id ? (
                <TextInput
                  value={draft}
                  onChangeText={setDraft}
                  onSubmitEditing={() => saveEdit(fact)}
                  onBlur={() => saveEdit(fact)}
                  autoFocus
                  style={styles.editInput}
                />
              ) : (
                <Pressable onPress={() => startEdit(fact)} style={styles.factTextWrap}>
                  <Text style={styles.factKey}>{fact.key.replace(/_/g, ' ').replace(/:/g, ': ')}</Text>
                  <Text style={styles.factValue}>{fact.value}</Text>
                  {fact.source === 'inferred' && (
                    <Text style={styles.inferredTag}>{t('lifeTwin.inferredTag')}</Text>
                  )}
                </Pressable>
              )}
              <Pressable onPress={() => handleDelete(fact)} hitSlop={8} accessibilityLabel={t('common.delete')}>
                <Ionicons name="trash-outline" size={18} color={colors.textSecondary} />
              </Pressable>
            </View>
          ))}
        </GlassSurface>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
    gap: spacing.sm,
  },
  subtitle: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  timelineLink: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    minHeight: 48,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    marginBottom: spacing.sm,
  },
  timelineLinkText: {
    ...typography.bodyBold,
    color: colors.textPrimary,
    flex: 1,
  },
  pressedDim: {
    opacity: 0.85,
  },
  card: {
    padding: spacing.md,
  },
  emptyText: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
  },
  domainTitle: {
    ...typography.sectionTitle,
    color: colors.primary,
    marginBottom: spacing.sm,
  },
  factRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  factTextWrap: {
    flex: 1,
  },
  factKey: {
    ...typography.caption,
    color: colors.textSecondary,
    textTransform: 'capitalize',
  },
  factValue: {
    ...typography.body,
    color: colors.textPrimary,
  },
  inferredTag: {
    ...typography.caption,
    color: colors.accent,
    marginTop: 2,
  },
  editInput: {
    ...typography.body,
    color: colors.textPrimary,
    flex: 1,
    borderBottomWidth: 1,
    borderBottomColor: colors.primary,
    paddingVertical: 2,
  },
  decisionStatus: {
    ...typography.caption,
    color: colors.accent,
    marginBottom: spacing.xs,
    textTransform: 'capitalize',
  },
  outcomeText: {
    ...typography.caption,
    color: colors.success,
    marginTop: spacing.xs,
  },
});
