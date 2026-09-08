import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { colors, typography } from '../theme/theme';

export default function SplashScreen() {
  const { t } = useTranslation();
  return (
    <LinearGradient
      colors={[colors.primary, colors.primaryDark]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={styles.wrap}
    >
      <Ionicons name="sparkles" size={40} color={colors.textInverse} />
      <Text style={styles.wordmark}>{t('common.appName')}</Text>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  wordmark: {
    ...typography.display,
    color: colors.textInverse,
  },
});
