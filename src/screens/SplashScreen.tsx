import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, Text } from 'react-native';
import { useTranslation } from 'react-i18next';
import CosmicBackground from '../components/CosmicBackground';
import { colors, typography } from '../theme/theme';

export default function SplashScreen() {
  const { t } = useTranslation();
  return (
    <CosmicBackground style={styles.wrap}>
      {/* Gold on the night-sky background (not a solid gold banner) — the
          old gold-to-gold gradient here left white text with nowhere
          readable to sit, and read as a different app than the rest of the
          "Astrolabe Glass" direction anyway. */}
      <Ionicons name="sparkles" size={40} color={colors.primary} />
      <Text style={styles.wordmark}>{t('common.appName')}</Text>
    </CosmicBackground>
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
