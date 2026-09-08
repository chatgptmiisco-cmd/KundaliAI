import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import React, { useCallback, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { getSubscription } from '../api/client';
import BirthDataFields from '../components/BirthDataFields';
import Card from '../components/Card';
import LanguageToggle from '../components/LanguageToggle';
import PrimaryButton from '../components/PrimaryButton';
import { useUserStore } from '../store/useUserStore';
import { BirthData } from '../types/kundali';
import { colors, spacing, typography } from '../theme/theme';

export default function ProfileScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const birthData = useUserStore((s) => s.birthData);
  const setBirthData = useUserStore((s) => s.setBirthData);
  const plan = useUserStore((s) => s.plan);
  const setPlan = useUserStore((s) => s.setPlan);
  const credits = useUserStore((s) => s.credits);
  const isPremium = useUserStore((s) => s.isPremium);
  const resetOnboarding = useUserStore((s) => s.resetOnboarding);
  const logOut = useUserStore((s) => s.logOut);

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState<BirthData>(birthData);

  useFocusEffect(
    useCallback(() => {
      getSubscription()
        .then((sub) => setPlan(sub.tier))
        .catch(() => {
          // Silent — Profile still shows the last-known plan if the server is unreachable.
        });
    }, []),
  );

  const handleEdit = () => {
    setDraft(birthData);
    setEditing(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await setBirthData(draft);
      setEditing(false);
      Alert.alert(t('common.save'), t('profile.savedMessage'));
    } catch (err: any) {
      Alert.alert(t('common.tryAgain'), err?.message ?? String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleLogOut = () => {
    Alert.alert(
      t('profile.logOutConfirmTitle'),
      t('profile.logOutConfirmMessage'),
      [
        { text: t('common.cancel'), style: 'cancel' },
        { text: t('profile.logOut'), style: 'destructive', onPress: () => logOut() },
      ],
    );
  };

  const handleRestartOnboarding = () => {
    Alert.alert(
      t('profile.restartOnboardingConfirmTitle'),
      t('profile.restartOnboardingConfirmMessage'),
      [
        { text: t('common.cancel'), style: 'cancel' },
        { text: t('profile.restartOnboarding'), style: 'destructive', onPress: () => resetOnboarding() },
      ],
    );
  };

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Card>
        <View style={styles.headerRow}>
          <Text style={styles.cardTitle}>{t('profile.birthDetailsTitle')}</Text>
          {!editing && (
            <PrimaryButton label={t('common.edit')} variant="outline" onPress={handleEdit} />
          )}
        </View>

        {editing ? (
          <BirthDataFields value={draft} onChange={setDraft} />
        ) : (
          <BulletValues birthData={birthData} />
        )}

        {editing && (
          <View style={styles.saveRow}>
            <PrimaryButton label={t('common.save')} onPress={handleSave} loading={saving} disabled={saving} />
          </View>
        )}
      </Card>

      <Card>
        <Text style={styles.cardTitle}>{t('profile.planLabel')}</Text>
        <Text style={styles.planValue}>{t(`plans.${plan}`)}</Text>
        <PrimaryButton
          label={t('common.upgrade')}
          variant="secondary"
          onPress={() => navigation.navigate('UpgradePlans')}
        />
      </Card>

      <Card>
        <View style={styles.creditsRow}>
          <Ionicons name="diamond-outline" size={22} color={colors.primary} />
          <Text style={styles.creditsText}>
            {isPremium ? t('profile.unlimitedCredits') : `${credits} ${t('profile.creditsLabel')}`}
          </Text>
        </View>
        <PrimaryButton
          label={t('profile.buyCredits')}
          variant="outline"
          onPress={() => navigation.navigate('PassStore')}
        />
      </Card>

      <Card>
        <Text style={styles.cardTitle}>{t('profile.languageLabel')}</Text>
        <LanguageToggle />
      </Card>

      <Card>
        <PrimaryButton label={t('profile.logOut')} variant="outline" onPress={handleLogOut} />
      </Card>

      <Card>
        <Text style={styles.cardTitle}>{t('profile.testingSectionTitle')}</Text>
        <PrimaryButton
          label={t('profile.restartOnboarding')}
          variant="outline"
          onPress={handleRestartOnboarding}
        />
      </Card>
    </ScrollView>
  );
}

function BulletValues({ birthData }: { birthData: BirthData }) {
  const { t } = useTranslation();
  const rows: [string, string][] = [
    [t('profile.nameLabel'), birthData.name],
    [t('profile.dateOfBirthLabel'), birthData.dateOfBirth],
    [t('profile.timeOfBirthLabel'), birthData.timeOfBirth],
    [t('profile.placeOfBirthLabel'), birthData.placeOfBirth],
  ];
  return (
    <View>
      {rows.map(([label, value]) => (
        <View key={label} style={styles.field}>
          <Text style={styles.fieldLabel}>{label}</Text>
          <Text style={styles.fieldValue}>{value || '—'}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  cardTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  field: {
    marginBottom: spacing.md,
  },
  fieldLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  fieldValue: {
    ...typography.bodyBold,
    color: colors.textPrimary,
  },
  saveRow: {
    marginTop: spacing.sm,
  },
  planValue: {
    ...typography.title,
    color: colors.primary,
    marginBottom: spacing.md,
  },
  creditsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  creditsText: {
    ...typography.bodyBold,
    color: colors.textPrimary,
  },
});
