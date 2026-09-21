import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { LinearGradient } from 'expo-linear-gradient';
import React, { useEffect, useRef, useState } from 'react';
import {
  Dimensions,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { getDailyReading, getFocusReadings, getNextOnboardingTopic } from '../api/client';
import Card from '../components/Card';
import DailyReadingSections from '../components/DailyReadingSections';
import ErrorState from '../components/ErrorState';
import LanguageToggle from '../components/LanguageToggle';
import LoadingState from '../components/LoadingState';
import { ONBOARDING_TOPICS, OnboardingTopic, TOPIC_SLUG } from '../data/onboardingTopics';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useInsightsStore } from '../store/useInsightsStore';
import { useKundaliStore } from '../store/useKundaliStore';
import { useUserStore } from '../store/useUserStore';
import { DailyReading, FocusAreaReading, PreferenceKey } from '../types/kundali';
import { colors, elevation, fontFamily, radius, spacing, typography } from '../theme/theme';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

function useLiveClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

interface QuickAction {
  key: string;
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
}

const PREFERENCE_ICONS: Record<PreferenceKey, keyof typeof Ionicons.glyphMap> = {
  family: 'people-outline',
  health: 'fitness-outline',
  career: 'briefcase-outline',
  marriageRelationships: 'heart-outline',
  friends: 'happy-outline',
};

// Frontend preference keys are camelCase; the backend's focus-area keys are
// the classical snake_case names — this is the one place that maps them.
const AREA_KEY_MAP: Record<PreferenceKey, string> = {
  family: 'family',
  health: 'health',
  career: 'career',
  marriageRelationships: 'marriage_relationships',
  friends: 'friends',
};

export default function HomeDashboardScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const insets = useSafeAreaInsets();
  const language = toContentLanguage(useUserStore((s) => s.language));
  // Defensive filter, in addition to the store-level migration: never let an
  // unrecognized preference value (e.g. stale data from before a rename)
  // reach the icon/area lookups below, which would throw.
  const preferences = useUserStore((s) => s.preferences).filter((p) => p in PREFERENCE_ICONS);

  // Still fetched (not rendered) purely to feed the Insights/notifications
  // badge — see useInsightsStore.generate(). The chart-level "at a glance"
  // card itself was removed from Home: it only duplicated the Kundali tab
  // and had nothing to do with today.
  const summary = useKundaliStore((s) => s.summary[language]);
  const fetchSummary = useKundaliStore((s) => s.fetchSummary);
  const identity = useKundaliStore((s) => s.identity);
  const fetchIdentity = useKundaliStore((s) => s.fetchIdentity);

  const unreadInsights = useInsightsStore((s) => s.unreadCount);
  const generateInsights = useInsightsStore((s) => s.generate);

  const [reading, setReading] = useState<DailyReading | null>(null);
  const [readingError, setReadingError] = useState(false);
  const [focusReadings, setFocusReadings] = useState<FocusAreaReading[] | null>(null);

  const [activeTab, setActiveTab] = useState(0);
  const pagerRef = useRef<ScrollView>(null);
  const now = useLiveClock();

  // Phase 7 — adaptive multi-session onboarding: null unless the backend
  // has something worth asking about right now (see onboarding_followup_
  // service). Fetched once per Home mount, same "silent on failure, card
  // just doesn't render" convention as everything else fetched here.
  const [nextOnboardingTopic, setNextOnboardingTopic] = useState<OnboardingTopic | null>(null);
  useEffect(() => {
    getNextOnboardingTopic()
      .then((result) => {
        if (!result.topic) return;
        const match = ONBOARDING_TOPICS.find((tp) => TOPIC_SLUG[tp.key] === result.topic);
        if (match) setNextOnboardingTopic(match.key);
      })
      .catch(() => {
        // Silent — no card if the server is unreachable.
      });
  }, []);

  useEffect(() => {
    fetchSummary(language);
  }, [language]);

  useEffect(() => {
    fetchIdentity();
  }, []);

  const loadReading = () => {
    setReadingError(false);
    getDailyReading(language)
      .then((data) => setReading(data))
      .catch(() => setReadingError(true));
  };

  useEffect(() => {
    loadReading();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language]);

  useEffect(() => {
    let cancelled = false;
    getFocusReadings(language)
      .then((data) => {
        if (!cancelled) setFocusReadings(data);
      })
      .catch(() => {
        if (!cancelled) setFocusReadings([]);
      });
    return () => {
      cancelled = true;
    };
  }, [language]);

  useEffect(() => {
    if (summary) {
      generateInsights(preferences, language, summary);
    }
  }, [summary, preferences, language]);

  const quickActions: QuickAction[] = [
    {
      key: 'kundali',
      icon: 'book-outline',
      label: t('common.seeFullKundali'),
      onPress: () => navigation.navigate('KundaliTab'),
    },
    {
      key: 'charts',
      icon: 'pie-chart-outline',
      label: t('home.chartsCardTitle'),
      onPress: () => navigation.navigate('ChartsTab'),
    },
    {
      key: 'gunaMilan',
      icon: 'heart-circle-outline',
      label: t('home.gunaMilanButton'),
      onPress: () => navigation.navigate('GunaMilan'),
    },
    {
      key: 'periods',
      icon: 'time-outline',
      label: t('home.seePeriods'),
      onPress: () => navigation.navigate('PeriodAnalysis'),
    },
  ];

  const tabs = [
    { key: 'today', label: t('home.todayCardTitle'), icon: 'today-outline' as const },
    ...preferences.map((p) => ({ key: p, label: t(`preferences.${p}`), icon: PREFERENCE_ICONS[p] })),
  ];

  const goToTab = (index: number) => {
    setActiveTab(index);
    pagerRef.current?.scrollTo({ x: index * SCREEN_WIDTH, animated: true });
  };

  const handleMomentumEnd = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const next = Math.round(e.nativeEvent.contentOffset.x / SCREEN_WIDTH);
    setActiveTab(next);
  };

  return (
    <View style={styles.screen}>
      {/* Cosmic violet-to-indigo, not the gold accent color — the hero's
          white text/icons throughout (wordmark, panchang row, notification
          and profile icons) need a dark-enough background to read against,
          which the gold family no longer is now that primary/primaryDark
          are both light-to-medium gold instead of dark maroon. */}
      <LinearGradient
        colors={['#3A2456', colors.background]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[styles.hero, { paddingTop: insets.top + spacing.sm }]}
      >
        <View style={styles.heroTopRow}>
          <View style={styles.wordmarkRow}>
            <Ionicons name="sparkles" size={18} color={colors.textInverse} />
            <Text style={styles.wordmark}>{t('common.appName')}</Text>
          </View>
          <View style={styles.heroActions}>
            <LanguageToggle inverse />
            <Pressable
              onPress={() => navigation.navigate('Insights')}
              accessibilityRole="button"
              accessibilityLabel={t('insights.screenTitle')}
              style={({ pressed }) => [
                styles.profileButton,
                pressed && styles.profileButtonPressed,
              ]}
            >
              <Ionicons name="notifications-outline" size={26} color={colors.textInverse} />
              {unreadInsights > 0 && (
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{unreadInsights}</Text>
                </View>
              )}
            </Pressable>
            <Pressable
              onPress={() => navigation.navigate('ProfileTab')}
              accessibilityRole="button"
              accessibilityLabel={t('home.profileButtonLabel')}
              style={({ pressed }) => [
                styles.profileButton,
                pressed && styles.profileButtonPressed,
              ]}
            >
              <Ionicons name="person-circle-outline" size={30} color={colors.textInverse} />
            </Pressable>
          </View>
        </View>
        <Text style={styles.greeting}>{t('home.greeting')}</Text>

        <View style={styles.panchangRow}>
          <View style={styles.panchangItem}>
            <Ionicons name="time-outline" size={14} color="rgba(255,255,255,0.7)" />
            <Text style={styles.panchangText}>
              {now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
            </Text>
          </View>
          <View style={styles.panchangItem}>
            <Ionicons name="calendar-outline" size={14} color="rgba(255,255,255,0.7)" />
            <Text style={styles.panchangText}>
              {now.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })}
            </Text>
          </View>
          {reading && (
            <View style={styles.panchangItem}>
              <Ionicons name="moon-outline" size={14} color="rgba(255,255,255,0.7)" />
              <Text style={styles.panchangText}>
                {reading.lunarMonth} · {t(`horoscope.paksha.${reading.paksha}`)} {reading.tithiName}
              </Text>
            </View>
          )}
        </View>

        {reading?.festival && (
          <View style={styles.festivalBanner}>
            <Ionicons name="sparkles" size={14} color={colors.accentDark} />
            <Text style={styles.festivalText}>{reading.festival}</Text>
          </View>
        )}
      </LinearGradient>

      {tabs.length > 1 && (
        <View style={styles.tabBar}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabBarContent}>
            {tabs.map((tab, i) => (
              <Pressable
                key={tab.key}
                onPress={() => goToTab(i)}
                accessibilityRole="button"
                accessibilityState={{ selected: i === activeTab }}
                style={[styles.tabChip, i === activeTab && styles.tabChipActive]}
              >
                <Ionicons name={tab.icon} size={15} color={i === activeTab ? colors.textOnPrimary : colors.textSecondary} />
                <Text style={[styles.tabChipText, i === activeTab && styles.tabChipTextActive]}>{tab.label}</Text>
              </Pressable>
            ))}
          </ScrollView>
        </View>
      )}

      <ScrollView
        ref={pagerRef}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={handleMomentumEnd}
        style={{ flex: 1 }}
      >
        <ScrollView style={{ width: SCREEN_WIDTH }} contentContainerStyle={styles.content}>
          {readingError && !reading && (
            <ErrorState
              title={t('kundali.errorTitle')}
              message={t('horoscope.errorMessage')}
              onRetry={loadReading}
            />
          )}
          {!reading && !readingError && <LoadingState message={t('horoscope.loadingMessage')} />}
          {reading && identity && (
            <Card style={styles.horoscopeHeaderCard}>
              <Text style={styles.horoscopeHeaderTitle}>{t('horoscope.todaysHoroscopeTitle')}</Text>
              <Text style={styles.horoscopeHeaderRashi}>
                {t('horoscope.yourRashiLabel', {
                  rashi: language === 'hi' ? identity.moonSign.signHi : identity.moonSign.signEn,
                })}
              </Text>
            </Card>
          )}
          {reading && <DailyReadingSections reading={reading} />}

          <View style={styles.quickActionsRow}>
            {quickActions.map((action) => (
              <Pressable
                key={action.key}
                onPress={action.onPress}
                accessibilityRole="button"
                accessibilityLabel={action.label}
                style={({ pressed }) => [styles.quickAction, pressed && styles.quickActionPressed]}
              >
                <Ionicons name={action.icon} size={24} color={colors.primary} />
                <Text style={styles.quickActionLabel} numberOfLines={2}>
                  {action.label}
                </Text>
              </Pressable>
            ))}
          </View>

          {nextOnboardingTopic && (
            <Pressable onPress={() => navigation.navigate('FollowUpQuestions', { topic: nextOnboardingTopic })}>
              <Card style={styles.followUpCard}>
                <View style={styles.followUpRow}>
                  <Ionicons name="chatbubble-ellipses-outline" size={22} color={colors.primary} />
                  <Text style={styles.followUpText}>
                    {t('home.followUpCardTitle', { topic: t(`onboardingTopics.${nextOnboardingTopic}`) })}
                  </Text>
                </View>
              </Card>
            </Pressable>
          )}
        </ScrollView>

        {preferences.map((pref) => {
          const areaKey = AREA_KEY_MAP[pref];
          const focusReading = focusReadings?.find((r) => r.area === areaKey) ?? null;
          return (
            <ScrollView key={pref} style={{ width: SCREEN_WIDTH }} contentContainerStyle={styles.content}>
              <Card style={styles.todayCard}>
                <View style={styles.todayHeaderRow}>
                  <Text style={styles.todayCardTitle}>{t(`preferences.${pref}`)}</Text>
                  {focusReading && <Text style={styles.todayRating}>{focusReading.rating}/10</Text>}
                </View>

                {focusReadings === null && <LoadingState message={t('common.loading')} />}

                {focusReadings !== null && !focusReading && (
                  <Text style={styles.body}>{t('kundali.errorMessage')}</Text>
                )}

                {focusReading && (
                  <>
                    <View style={styles.tagsRow}>
                      <View style={styles.tag}>
                        <Text style={styles.tagText}>{focusReading.theme}</Text>
                      </View>
                    </View>
                    <Text style={styles.body}>{focusReading.summary}</Text>
                  </>
                )}
              </Card>

              {focusReading && (
                <>
                  <Card>
                    <Text style={styles.focusSectionLabel}>{t('home.focusMeaningLabel')}</Text>
                    <Text style={styles.body}>{focusReading.meaning}</Text>
                  </Card>

                  <Card style={styles.avoidCard}>
                    <Text style={[styles.focusSectionLabel, styles.avoidLabel]}>{t('home.focusAvoidLabel')}</Text>
                    <Text style={styles.body}>{focusReading.avoidToday}</Text>
                  </Card>

                  <Card style={styles.doCard}>
                    <Text style={[styles.focusSectionLabel, styles.doLabel]}>{t('home.focusDoLabel')}</Text>
                    <Text style={styles.body}>{focusReading.focusToday}</Text>
                  </Card>

                  {focusReading.transitNote && (
                    <Card>
                      <Text style={styles.focusSectionLabel}>{t('horoscope.transitHighlightLabel')}</Text>
                      <Text style={styles.body}>{focusReading.transitNote}</Text>
                    </Card>
                  )}
                </>
              )}
            </ScrollView>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  hero: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.lg,
    borderBottomLeftRadius: radius.xl,
    borderBottomRightRadius: radius.xl,
    ...elevation.raised,
  },
  heroTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  wordmarkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  wordmark: {
    ...typography.bodyBold,
    color: colors.textInverse,
  },
  heroActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  profileButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.pill,
  },
  profileButtonPressed: {
    backgroundColor: 'rgba(255,255,255,0.15)',
  },
  greeting: {
    ...typography.display,
    color: colors.textInverse,
  },
  panchangRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  panchangItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  panchangText: {
    ...typography.caption,
    color: 'rgba(255,255,255,0.75)',
  },
  festivalBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    alignSelf: 'flex-start',
    marginTop: spacing.sm,
    backgroundColor: 'rgba(255,255,255,0.14)',
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
  },
  festivalText: {
    ...typography.caption,
    color: colors.textInverse,
    fontFamily: fontFamily.bold,
  },
  tabBar: {
    backgroundColor: colors.background,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  tabBarContent: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: spacing.xs,
  },
  tabChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tabChipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  tabChipText: {
    ...typography.caption,
    color: colors.textSecondary,
    fontFamily: fontFamily.bold,
  },
  tabChipTextActive: {
    color: colors.textOnPrimary, // active chip bg is now light gold, textInverse would wash out
  },
  content: {
    padding: spacing.md,
    paddingBottom: spacing.xxl,
  },
  cardTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  body: {
    ...typography.body,
    color: colors.textPrimary,
  },
  todayCard: {
    borderWidth: 1.5,
    borderColor: colors.accentLight,
  },
  todayCardTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  todayHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  todayRating: {
    ...typography.title,
    color: colors.primary,
  },
  tagsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  tag: {
    backgroundColor: colors.background,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  tagText: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  focusSectionLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    fontFamily: fontFamily.bold,
    marginBottom: spacing.xs,
    textTransform: 'uppercase',
  },
  avoidCard: {
    backgroundColor: colors.premiumLight,
    borderColor: colors.premium,
    borderWidth: 1,
  },
  avoidLabel: {
    color: colors.premium,
  },
  doCard: {
    backgroundColor: colors.successLight,
    borderColor: colors.success,
    borderWidth: 1,
  },
  doLabel: {
    color: colors.success,
  },
  horoscopeHeaderCard: {
    backgroundColor: colors.primaryLight,
    borderColor: colors.primary,
    borderWidth: 1,
    alignItems: 'center',
  },
  horoscopeHeaderTitle: {
    ...typography.sectionTitle,
    color: colors.textOnPrimary, // sits on primaryLight card bg, now light-on-light with primaryDark
  },
  horoscopeHeaderRashi: {
    ...typography.title,
    color: colors.textOnPrimary, // same primaryLight card bg — primary text is now too light too
    marginTop: spacing.xs,
    fontFamily: fontFamily.displayBold,
  },
  quickActionsRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  quickAction: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xs,
    ...elevation.card,
  },
  quickActionPressed: {
    backgroundColor: colors.surfaceMuted,
  },
  quickActionLabel: {
    ...typography.caption,
    color: colors.textPrimary,
    textAlign: 'center',
  },
  followUpCard: {
    marginTop: spacing.md,
  },
  followUpRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  followUpText: {
    ...typography.bodyBold,
    color: colors.textPrimary,
    flex: 1,
  },
  badge: {
    position: 'absolute',
    top: 4,
    right: 4,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 3,
  },
  badgeText: {
    fontSize: 11,
    fontFamily: fontFamily.bold,
    color: colors.textInverse,
  },
});
