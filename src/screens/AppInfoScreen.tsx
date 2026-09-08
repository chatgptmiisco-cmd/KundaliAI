import { useNavigation } from '@react-navigation/native';
import React, { useRef, useState } from 'react';
import { Dimensions, NativeScrollEvent, NativeSyntheticEvent, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import PrimaryButton from '../components/PrimaryButton';
import { colors, fontFamily, radius, spacing, typography } from '../theme/theme';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

interface SlideCheck {
  title: string;
  desc: string;
}

interface Slide {
  eyebrow: string;
  title: string;
  checks: SlideCheck[];
}

export default function AppInfoScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const scrollRef = useRef<ScrollView>(null);
  const [index, setIndex] = useState(0);

  const slides = t('appInfo.slides', { returnObjects: true }) as Slide[];
  const isLast = index === slides.length - 1;

  const goToAuth = () => navigation.navigate('Auth');

  const goToSlide = (next: number) => {
    setIndex(next);
    scrollRef.current?.scrollTo({ x: next * SCREEN_WIDTH, animated: true });
  };

  const handleMomentumEnd = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const next = Math.round(e.nativeEvent.contentOffset.x / SCREEN_WIDTH);
    setIndex(next);
  };

  return (
    <View style={styles.screen}>
      <View style={styles.topRow}>
        <View style={styles.dots}>
          {slides.map((_, i) => (
            <View key={i} style={[styles.dot, i === index && styles.dotActive]} />
          ))}
        </View>
        {!isLast && (
          <Pressable onPress={goToAuth} accessibilityRole="button">
            <Text style={styles.skip}>{t('appInfo.skip')}</Text>
          </Pressable>
        )}
      </View>

      <ScrollView
        ref={scrollRef}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={handleMomentumEnd}
        style={{ flex: 1 }}
      >
        {slides.map((slide, i) => (
          <View key={i} style={[styles.slide, { width: SCREEN_WIDTH }]}>
            <Text style={styles.eyebrow}>{slide.eyebrow}</Text>
            <Text style={styles.title}>{slide.title}</Text>

            <View style={styles.checks}>
              {slide.checks.map((c) => (
                <View key={c.title} style={styles.checkRow}>
                  <View style={styles.checkIcon}>
                    <Text style={styles.checkIconText}>✓</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.checkTitle}>{c.title}</Text>
                    <Text style={styles.checkDesc}>{c.desc}</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        ))}
      </ScrollView>

      <View style={styles.footer}>
        <PrimaryButton
          label={isLast ? t('appInfo.getStarted') : t('appInfo.continueButton')}
          onPress={() => (isLast ? goToAuth() : goToSlide(index + 1))}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
  },
  dots: {
    flexDirection: 'row',
    gap: 7,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.border,
  },
  dotActive: {
    width: 24,
    backgroundColor: colors.accent,
  },
  skip: {
    ...typography.bodyBold,
    color: colors.textSecondary,
  },
  slide: {
    padding: spacing.lg,
    paddingTop: spacing.xl,
  },
  eyebrow: {
    ...typography.caption,
    color: colors.accentDark,
    fontFamily: fontFamily.bold,
    letterSpacing: 1,
    textTransform: 'uppercase',
    marginBottom: spacing.sm,
  },
  title: {
    ...typography.display,
    color: colors.textPrimary,
    marginBottom: spacing.xl,
  },
  checks: {
    gap: spacing.lg,
  },
  checkRow: {
    flexDirection: 'row',
    gap: spacing.md,
    alignItems: 'flex-start',
  },
  checkIcon: {
    width: 28,
    height: 28,
    borderRadius: radius.sm,
    backgroundColor: colors.successLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkIconText: {
    color: colors.success,
    fontFamily: fontFamily.bold,
    fontSize: 13,
  },
  checkTitle: {
    ...typography.bodyBold,
    color: colors.textPrimary,
  },
  checkDesc: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: 2,
  },
  footer: {
    padding: spacing.lg,
  },
});
