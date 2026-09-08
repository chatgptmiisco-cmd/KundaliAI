import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { checkoutSubscription } from '../api/client';
import BulletList from '../components/BulletList';
import Card from '../components/Card';
import PrimaryButton from '../components/PrimaryButton';
import { useUserStore } from '../store/useUserStore';
import { PlanTier } from '../types/kundali';
import { colors, fontFamily, radius, spacing, typography } from '../theme/theme';

const PLAN_ORDER: PlanTier[] = ['free', 'insight', 'strategy'];

export default function UpgradePlansScreen() {
  const { t } = useTranslation();
  const plan = useUserStore((s) => s.plan);
  const setPlan = useUserStore((s) => s.setPlan);
  const [loadingTier, setLoadingTier] = useState<PlanTier | null>(null);

  const handleChoose = async (tier: PlanTier) => {
    if (tier === 'free') return; // downgrading isn't wired up on the backend yet
    setLoadingTier(tier);
    try {
      const result = await checkoutSubscription(tier, 'monthly');
      setPlan(tier);
      Alert.alert(t('plans.choosePlan'), result.note);
    } catch (err: any) {
      Alert.alert(t('common.tryAgain'), err?.message ?? String(err));
    } finally {
      setLoadingTier(null);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.content}>
      {PLAN_ORDER.map((tier) => {
        const isCurrent = plan === tier;
        const features = t(`plans.${tier}Features`, { returnObjects: true }) as string[];
        return (
          <Card
            key={tier}
            style={[styles.planCard, isCurrent && styles.currentPlanCard] as any}
          >
            <View style={styles.planHeader}>
              <Text style={styles.planTitle}>{t(`plans.${tier}`)}</Text>
              {isCurrent && (
                <View style={styles.currentPill}>
                  <Ionicons name="checkmark-circle" size={16} color={colors.success} />
                  <Text style={styles.currentPillText}>{t('plans.currentPlan')}</Text>
                </View>
              )}
            </View>
            <BulletList items={features} />
            {!isCurrent && tier !== 'free' && (
              <PrimaryButton
                label={t('plans.choosePlan')}
                variant="primary"
                onPress={() => handleChoose(tier)}
                loading={loadingTier === tier}
                disabled={loadingTier !== null}
              />
            )}
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
  planCard: {},
  currentPlanCard: {
    borderColor: colors.success,
    borderWidth: 2,
  },
  planHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  planTitle: {
    ...typography.title,
    color: colors.textPrimary,
  },
  currentPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: colors.successLight,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  currentPillText: {
    ...typography.caption,
    color: colors.success,
    fontFamily: fontFamily.bold,
  },
});
