import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useNavigation } from '@react-navigation/native';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useUserStore } from '../store/useUserStore';
import { useVoiceStore } from '../store/useVoiceStore';
import { colors, fontFamily, minTouchTarget, radius, spacing, typography } from '../theme/theme';
import PremiumModal from './PremiumModal';
import { trackEvent } from '../analytics/analytics';

interface Props {
  label: string;
  title: string;
  text: string;
  analyticsSource: 'kundali' | 'manglik';
  compact?: boolean;
}

export default function SpeakerButton({ label, title, text, analyticsSource, compact }: Props) {
  const { t } = useTranslation();
  const isPremium = useUserStore((s) => s.isPremium);
  const language = useUserStore((s) => s.language);
  const play = useVoiceStore((s) => s.play);
  const [modalVisible, setModalVisible] = useState(false);
  const navigation = useNavigation<any>();

  const handlePress = () => {
    if (!isPremium) {
      setModalVisible(true);
      return;
    }
    play({ title, text, language: toContentLanguage(language) });
    trackEvent('voice_explanation_played', { source: analyticsSource });
  };

  return (
    <>
      <Pressable
        onPress={handlePress}
        accessibilityRole="button"
        accessibilityLabel={label}
        style={({ pressed }) => [
          styles.button,
          compact && styles.compact,
          pressed && styles.pressed,
        ]}
      >
        <Ionicons
          name={isPremium ? 'volume-high' : 'volume-high-outline'}
          size={20}
          color={colors.primary}
        />
        <Text style={styles.label} numberOfLines={1}>
          {label}
        </Text>
        {!isPremium && (
          <View style={styles.premiumPill}>
            <Text style={styles.premiumPillText}>{t('common.premiumFeature')}</Text>
          </View>
        )}
      </Pressable>
      <PremiumModal
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        onUpgrade={() => {
          setModalVisible(false);
          navigation.navigate('UpgradePlans');
        }}
      />
    </>
  );
}

const styles = StyleSheet.create({
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: minTouchTarget,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.md,
    gap: spacing.xs,
    flexShrink: 1,
  },
  compact: {
    minHeight: 40,
  },
  pressed: {
    backgroundColor: colors.surfaceMuted,
  },
  label: {
    ...typography.caption,
    color: colors.primary,
    fontFamily: fontFamily.bold,
  },
  premiumPill: {
    backgroundColor: colors.premiumLight,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    marginLeft: spacing.xs,
  },
  premiumPillText: {
    fontSize: 11,
    fontFamily: fontFamily.bold,
    color: colors.premium,
  },
});
