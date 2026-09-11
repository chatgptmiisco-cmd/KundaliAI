import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import React, { useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { RISHIS, RishiId } from '../constants/rishis';
import { colors, elevation, fontFamily, radius, spacing, typography } from '../theme/theme';

interface Props {
  activeId: RishiId;
  onSelect: (id: RishiId) => void;
}

/** Header trigger + floating list for switching which Rishi you're talking
 * to, without leaving the chat screen — reuses the same backdrop-Modal
 * pattern as DefinitionTooltip/PremiumModal rather than a new UI paradigm. */
export default function RishiSwitcher({ activeId, onSelect }: Props) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  const active = RISHIS.find((r) => r.id === activeId) ?? RISHIS[0];

  return (
    <>
      <Pressable
        onPress={() => setVisible(true)}
        accessibilityRole="button"
        accessibilityLabel={t('rishiPicker.switchTrigger', { name: active.name }) as string}
        style={({ pressed }) => [styles.trigger, pressed && styles.triggerPressed]}
      >
        <LinearGradient colors={active.gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.portrait}>
          <Text style={styles.portraitText}>{active.initial}</Text>
        </LinearGradient>
        <View style={{ flex: 1 }}>
          <View style={styles.nameRow}>
            <Text style={styles.name}>{active.name}</Text>
            <Ionicons name="chevron-down" size={16} color={colors.textSecondary} />
          </View>
          <Text style={styles.focus}>{t(`rishiPicker.${active.id}.focus`)}</Text>
        </View>
      </Pressable>

      <Modal transparent visible={visible} animationType="fade" onRequestClose={() => setVisible(false)}>
        <Pressable style={styles.backdrop} onPress={() => setVisible(false)}>
          <Pressable style={styles.card} onPress={() => {}}>
            <View style={styles.cardHandle} />
            <Text style={styles.cardTitle}>{t('rishiPicker.screenTitle')}</Text>
            <Text style={styles.cardSubtitle}>{t('rishiPicker.subtitle')}</Text>
            <ScrollView style={styles.list} showsVerticalScrollIndicator={false}>
              {RISHIS.map((rishi, i) => {
                const isActive = rishi.id === activeId;
                return (
                  <Pressable
                    key={rishi.id}
                    onPress={() => {
                      setVisible(false);
                      onSelect(rishi.id);
                    }}
                    accessibilityRole="button"
                    accessibilityLabel={rishi.name}
                    style={({ pressed }) => [
                      styles.row,
                      i > 0 && styles.rowDivider,
                      isActive && styles.rowActive,
                      pressed && styles.rowPressed,
                    ]}
                  >
                    <LinearGradient colors={rishi.gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.portrait}>
                      <Text style={styles.portraitText}>{rishi.initial}</Text>
                    </LinearGradient>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.name}>{rishi.name}</Text>
                      <Text style={styles.focus}>{t(`rishiPicker.${rishi.id}.focus`)}</Text>
                    </View>
                    {isActive && <Ionicons name="checkmark-circle" size={22} color={rishi.gradient[1]} />}
                  </Pressable>
                );
              })}
            </ScrollView>
            <Text style={styles.disclaimer}>{t('rishiPicker.disclaimer')}</Text>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    flex: 1,
    borderRadius: radius.md,
  },
  triggerPressed: {
    backgroundColor: colors.background,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  portrait: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: elevation.card.shadowColor,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: elevation.card.shadowOpacity,
    shadowRadius: elevation.card.shadowRadius,
    elevation: elevation.card.elevation,
  },
  portraitText: {
    fontSize: 16,
    fontFamily: fontFamily.displayBold,
    color: colors.textInverse,
  },
  name: {
    ...typography.bodyBold,
    color: colors.textPrimary,
  },
  focus: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(43,36,28,0.45)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.lg,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.lg,
    width: '100%',
    maxWidth: 400,
    maxHeight: '80%',
    ...elevation.raised,
  },
  cardHandle: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.border,
    marginBottom: spacing.md,
  },
  cardTitle: {
    ...typography.title,
    color: colors.textPrimary,
  },
  cardSubtitle: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: 2,
    marginBottom: spacing.md,
  },
  list: {
    flexGrow: 0,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
    borderRadius: radius.md,
  },
  rowDivider: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  rowActive: {
    backgroundColor: colors.background,
  },
  rowPressed: {
    backgroundColor: colors.surfaceMuted,
  },
  disclaimer: {
    ...typography.caption,
    color: colors.textSecondary,
    textAlign: 'center',
    marginTop: spacing.md,
  },
});
