import { useNavigation } from '@react-navigation/native';
import { LinearGradient } from 'expo-linear-gradient';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import LanguageToggle from '../components/LanguageToggle';
import PlanetLoader from '../components/PlanetLoader';
import PrimaryButton from '../components/PrimaryButton';
import StarField from '../components/StarField';
import { colors, fontFamily, spacing, typography } from '../theme/theme';

export default function WelcomeScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const insets = useSafeAreaInsets();

  return (
    <LinearGradient
      colors={['#241d3d', colors.primaryDark, colors.primary]}
      start={{ x: 0.1, y: 0 }}
      end={{ x: 0.9, y: 1 }}
      style={styles.screen}
    >
      <StarField />

      <View style={[styles.langRow, { top: insets.top + spacing.sm }]}>
        <LanguageToggle inverse />
      </View>

      <View style={styles.center}>
        <PlanetLoader size={220} dark />
        <Text style={styles.wordmark}>
          Kundali<Text style={styles.wordmarkAccent}>AI</Text>
        </Text>
        <Text style={styles.title}>{t('onboarding.welcomeTitle')}</Text>
        <Text style={styles.subtitle}>{t('onboarding.welcomeSubtitle')}</Text>
      </View>

      <View style={styles.footer}>
        <PrimaryButton label={t('onboarding.getStarted')} onPress={() => navigation.navigate('AppInfo')} />
      </View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    paddingHorizontal: spacing.lg,
  },
  langRow: {
    position: 'absolute',
    right: spacing.md,
    zIndex: 2,
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  wordmark: {
    marginTop: spacing.xl,
    fontSize: 40,
    fontFamily: fontFamily.displayExtraBold,
    color: colors.textInverse,
    letterSpacing: -1,
  },
  wordmarkAccent: {
    color: '#efc77e',
  },
  title: {
    ...typography.title,
    color: colors.textInverse,
    textAlign: 'center',
    marginTop: spacing.md,
  },
  subtitle: {
    ...typography.body,
    color: 'rgba(255,255,255,0.62)',
    textAlign: 'center',
    marginTop: spacing.sm,
    maxWidth: 320,
  },
  footer: {
    paddingBottom: spacing.xl,
  },
});
