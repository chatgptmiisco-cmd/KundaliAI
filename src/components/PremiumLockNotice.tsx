import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { colors, radius, spacing, typography } from '../theme/theme';
import PrimaryButton from './PrimaryButton';

interface Props {
  message: string;
  unlockLabel: string;
}

export default function PremiumLockNotice({ message, unlockLabel }: Props) {
  const navigation = useNavigation<any>();
  return (
    <View style={styles.wrap}>
      <Ionicons name="lock-closed-outline" size={28} color={colors.premium} />
      <Text style={styles.message}>{message}</Text>
      <PrimaryButton
        label={unlockLabel}
        variant="secondary"
        onPress={() => navigation.navigate('UpgradePlans')}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: colors.premiumLight,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.premium,
    padding: spacing.lg,
    alignItems: 'center',
    gap: spacing.sm,
  },
  message: {
    ...typography.body,
    color: colors.premium,
    textAlign: 'center',
    marginBottom: spacing.xs,
  },
});
