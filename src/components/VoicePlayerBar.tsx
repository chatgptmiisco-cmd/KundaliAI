import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useVoiceStore } from '../store/useVoiceStore';
import { colors, elevation, radius, spacing, typography } from '../theme/theme';

export default function VoicePlayerBar() {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const { visible, title, playing, elapsed, duration, toggle, close } = useVoiceStore();

  if (!visible) return null;

  const progress = duration > 0 ? Math.min(1, elapsed / duration) : 0;

  return (
    <View style={[styles.wrap, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
      <View style={styles.row}>
        <Pressable
          onPress={toggle}
          accessibilityRole="button"
          accessibilityLabel={playing ? t('common.pause') : t('common.play')}
          style={styles.playButton}
        >
          <Ionicons name={playing ? 'pause' : 'play'} size={24} color={colors.textInverse} />
        </Pressable>

        <View style={styles.middle}>
          <Text style={styles.title} numberOfLines={1}>
            {title}
          </Text>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${progress * 100}%` }]} />
          </View>
        </View>

        <Pressable
          onPress={close}
          accessibilityRole="button"
          accessibilityLabel={t('common.close')}
          style={styles.closeButton}
        >
          <Ionicons name="close" size={22} color={colors.textSecondary} />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    shadowColor: elevation.raised.shadowColor,
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: elevation.raised.shadowOpacity,
    shadowRadius: elevation.raised.shadowRadius,
    elevation: elevation.raised.elevation,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  playButton: {
    width: 48,
    height: 48,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  middle: {
    flex: 1,
  },
  title: {
    ...typography.bodyBold,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  track: {
    height: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    backgroundColor: colors.accent,
    borderRadius: radius.pill,
  },
  closeButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
