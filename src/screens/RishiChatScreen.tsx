import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';
import { LinearGradient } from 'expo-linear-gradient';
import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { postChatMessage } from '../api/client';
import PremiumModal from '../components/PremiumModal';
import RishiSwitcher from '../components/RishiSwitcher';
import { ALL_FEATURES_FREE } from '../config/env';
import { DEFAULT_RISHI_ID, findRishi, RishiId } from '../constants/rishis';
import { getRishiReply } from '../data/chatReplies';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useChatStore } from '../store/useChatStore';
import { useUserStore } from '../store/useUserStore';
import { useVoiceStore } from '../store/useVoiceStore';
import { colors, elevation, fontFamily, minTouchTarget, radius, spacing, typography } from '../theme/theme';

type Phase = 'idle' | 'thinking';

// The center tab-bar button (see MainTabs.CenterMicButton) is 68px tall but
// popped up `top: -22` out of its ~50px-tall cell, so roughly 30px of it
// protrudes above the tab bar's own top edge — directly into this screen's
// bottom edge if nothing reserves space for it. This clearance is extra
// padding on TOP of whatever the tab bar's normal flex height already
// reserves, sized with margin to spare so the input row never sits behind it.
const TAB_BAR_BUTTON_CLEARANCE = 40;
// Below this distance (px) from the true bottom of the message list, treat
// the user as "caught up" — new replies auto-scroll into view and the
// floating scroll-to-latest button stays hidden. Beyond it (whether they've
// scrolled up one message or all the way to the first message), new
// messages no longer yank them away from what they're reading, and the
// button appears so they can jump back down on their own terms.
const NEAR_BOTTOM_THRESHOLD = 120;

export default function RishiChatScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  // No picker screen anymore — chat is the entry point, defaulting to the
  // generalist Vyasa persona; a rishiId param (still supported) only ever
  // arrives if something deep-links straight to a specific Rishi.
  const [activeRishiId, setActiveRishiId] = useState<RishiId>(route.params?.rishiId ?? DEFAULT_RISHI_ID);
  const rishi = findRishi(activeRishiId);

  const language = useUserStore((s) => s.language);
  const contentLanguage = toContentLanguage(language);
  const plan = useUserStore((s) => s.plan);
  const isPremium = useUserStore((s) => s.isPremium);
  const credits = useUserStore((s) => s.credits);
  const spendCredit = useUserStore((s) => s.spendCredit);
  const speak = useVoiceStore((s) => s.play);

  const messages = useChatStore((s) => s.messagesByRishi[rishi.id]) ?? [];
  const initConversation = useChatStore((s) => s.initConversation);
  const addMessage = useChatStore((s) => s.addMessage);

  const [phase, setPhase] = useState<Phase>('idle');
  const [typedInput, setTypedInput] = useState('');
  const [lockVisible, setLockVisible] = useState(false);
  // Shown only once earlier messages have scrolled out of view below the
  // current screen — lets the user jump back to the latest reply instead of
  // manually scrolling down. Works the same whether they're reading the
  // very first message or just one message behind the latest: it's purely
  // "how far from the true bottom," not tied to which message is on screen.
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  // A ref (not state) so the onContentSizeChange callback below always
  // reads the latest value without re-subscribing — whether a NEW message
  // should auto-scroll into view depends on where the user was a moment
  // ago, not on a value captured when this render happened.
  const isNearBottomRef = useRef(true);
  const scrollRef = useRef<ScrollView>(null);

  const handleMessagesScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
    const distanceFromBottom = contentSize.height - (contentOffset.y + layoutMeasurement.height);
    const nearBottom = distanceFromBottom <= NEAR_BOTTOM_THRESHOLD;
    isNearBottomRef.current = nearBottom;
    setShowScrollToBottom(!nearBottom);
  };

  const scrollToBottom = () => scrollRef.current?.scrollToEnd({ animated: true });

  const handleMessagesContentSizeChange = () => {
    // Only follow new content automatically if the user was already caught
    // up — otherwise a reply arriving while they're reading an earlier
    // message would yank them away from it. They keep control either way:
    // caught up → stays caught up; scrolled back → the floating arrow (not
    // a forced jump) is how they choose to catch up.
    if (isNearBottomRef.current) {
      scrollRef.current?.scrollToEnd({ animated: true });
    }
  };

  useEffect(() => {
    // The native header is hidden (see RishiStack) — this only sets the
    // back-button/a11y title, not anything visibly shown.
    navigation.setOptions({ title: rishi.name });
    initConversation(rishi.id, t(`rishiPicker.${rishi.id}.greeting`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rishi.id]);

  const sendToAssistant = async (text: string) => {
    if (!text.trim()) return;

    // Sending a message always brings the user back to "live" — their own
    // message, then the reply, should both scroll into view even if they'd
    // scrolled up to re-read something earlier.
    isNearBottomRef.current = true;
    setShowScrollToBottom(false);

    // Strategy subscribers get the real Claude-backed astrologer (backend-
    // gated at /chat/astro); everyone else keeps the local, credit-metered
    // canned replies for this Rishi's tone. ALL_FEATURES_FREE unlocks the
    // real path for everyone while plans aren't live yet.
    const hasStrategyAccess = plan === 'strategy' || ALL_FEATURES_FREE;
    if (!hasStrategyAccess) {
      const ok = spendCredit();
      if (!ok) {
        setLockVisible(true);
        return;
      }
    }

    addMessage(rishi.id, { id: `u-${Date.now()}`, role: 'user', text, createdAt: Date.now() });

    let reply: string;
    let answeredByRishiId: string | undefined;
    if (hasStrategyAccess) {
      setPhase('thinking');
      try {
        const res = await postChatMessage(text, contentLanguage, rishi.id);
        reply = res.reply;
        answeredByRishiId = res.answeredByRishiId;
      } catch {
        const assistantIndex = messages.filter((m) => m.role === 'assistant').length;
        reply = getRishiReply(rishi.tone, assistantIndex, contentLanguage);
      }
    } else {
      const assistantIndex = messages.filter((m) => m.role === 'assistant').length;
      reply = getRishiReply(rishi.tone, assistantIndex, contentLanguage);
    }

    addMessage(rishi.id, { id: `a-${Date.now()}`, role: 'assistant', text: reply, createdAt: Date.now(), answeredByRishiId });
    setPhase('idle');
    // No auto-play here — replies stay text-only until the user taps the
    // listen icon on a specific message (see the message list below).
  };

  const handleMicPress = () => {
    Alert.alert(t('voiceChat.comingSoonTitle'), t('voiceChat.comingSoonMessage'));
  };

  const handleSendTyped = async () => {
    const text = typedInput.trim();
    if (!text) return;
    setTypedInput('');
    await sendToAssistant(text);
  };

  const quickPrompts = [t('rishi.promptWeek'), t('rishi.promptDasha'), t('rishi.promptCareer'), t('rishi.promptPast')];
  const micLabel = phase === 'thinking' ? t('voiceChat.thinking') : t('voiceChat.tapToAsk');
  const micBusy = phase === 'thinking';

  return (
    <View style={styles.screen}>
      <View style={styles.rishiHeader}>
        <RishiSwitcher activeId={rishi.id} onSelect={setActiveRishiId} />
        <View style={styles.creditsPill}>
          <Ionicons name="diamond-outline" size={13} color={colors.primary} />
          <Text style={styles.creditsText}>
            {isPremium ? t('rishi.unlimitedMessages') : t('rishi.freeMessagesLeft', { count: credits })}
          </Text>
        </View>
      </View>

      <View style={styles.messagesWrap}>
        <ScrollView
          ref={scrollRef}
          style={styles.messages}
          contentContainerStyle={styles.messagesContent}
          onContentSizeChange={handleMessagesContentSizeChange}
          onScroll={handleMessagesScroll}
          scrollEventThrottle={100}
        >
          {messages.map((m) =>
            m.role === 'user' ? (
              <LinearGradient
                key={m.id}
                colors={[colors.primary, colors.primaryDark]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={[styles.bubble, styles.bubbleUser]}
              >
                <Text style={[styles.bubbleText, styles.bubbleTextUser]}>{m.text}</Text>
              </LinearGradient>
            ) : (
              <View key={m.id} style={[styles.bubble, styles.bubbleAssistant]}>
                <Text style={styles.bubbleText}>{m.text}</Text>
                <View style={styles.assistantFooter}>
                  <Pressable
                    onPress={() => speak({ title: rishi.name, text: m.text, language: contentLanguage })}
                    accessibilityRole="button"
                    accessibilityLabel={t('rishi.listenToReply')}
                    style={styles.listenButton}
                    hitSlop={8}
                  >
                    <Ionicons name="volume-medium-outline" size={18} color={colors.primary} />
                    <Text style={styles.listenButtonText}>{t('rishi.listenToReply')}</Text>
                  </Pressable>
                  {!!m.answeredByRishiId && (
                    <View style={[styles.answeredByBadge, { backgroundColor: findRishi(m.answeredByRishiId).gradient[0] + '33' }]}>
                      <Text style={[styles.answeredByText, { color: findRishi(m.answeredByRishiId).gradient[1] }]}>
                        {t('rishi.answeredBy', { name: findRishi(m.answeredByRishiId).name })}
                      </Text>
                    </View>
                  )}
                </View>
              </View>
            )
          )}
        </ScrollView>

        {showScrollToBottom && (
          <Pressable
            onPress={scrollToBottom}
            accessibilityRole="button"
            accessibilityLabel={t('rishi.scrollToLatest')}
            style={({ pressed }) => [styles.floatingButtonWrap, pressed && styles.pressedDim]}
          >
            <LinearGradient colors={rishi.gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.scrollToBottomButton}>
              <Ionicons name="arrow-down" size={20} color={colors.textInverse} />
            </LinearGradient>
          </Pressable>
        )}
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.promptsRow} contentContainerStyle={{ gap: spacing.xs, paddingHorizontal: spacing.md }}>
        {quickPrompts.map((p) => (
          <Pressable key={p} onPress={() => sendToAssistant(p)} style={styles.promptChip}>
            <Text style={styles.promptChipText}>{p}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <View style={styles.typedRow}>
        <TextInput
          value={typedInput}
          onChangeText={setTypedInput}
          placeholder={micBusy ? micLabel : (t('voiceChat.typeInsteadPlaceholder') as string)}
          placeholderTextColor={colors.textSecondary}
          editable={!micBusy}
          style={styles.typedInput}
          onSubmitEditing={handleSendTyped}
        />
        {/* One button on the right, like any standard chat composer: mic
            when the field is empty, send when there's something to send —
            never two separate buttons competing for the same spot. */}
        <Pressable
          onPress={typedInput.trim() ? handleSendTyped : handleMicPress}
          disabled={micBusy}
          accessibilityRole="button"
          accessibilityLabel={typedInput.trim() ? t('rishi.send') : micLabel}
          style={({ pressed }) => [pressed && styles.pressedDim]}
        >
          <LinearGradient
            colors={rishi.gradient}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={[styles.composerAction, micBusy && styles.micButtonBusy]}
          >
            {micBusy ? (
              <ActivityIndicator size="small" color={colors.textInverse} />
            ) : (
              <Ionicons name={typedInput.trim() ? 'arrow-up' : 'mic'} size={20} color={colors.textInverse} />
            )}
          </LinearGradient>
        </Pressable>
      </View>

      <PremiumModal
        visible={lockVisible}
        onClose={() => setLockVisible(false)}
        onUpgrade={() => {
          setLockVisible(false);
          navigation.navigate('UpgradePlans');
        }}
        message={t('rishi.outOfCreditsMessage') as string}
        icon="mic"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  rishiHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.surface,
    // A soft cast shadow instead of a hard 1px line reads as a deliberate
    // elevated panel rather than a wireframe divider.
    shadowColor: elevation.card.shadowColor,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: elevation.card.shadowOpacity,
    shadowRadius: elevation.card.shadowRadius,
    elevation: elevation.card.elevation,
    zIndex: 1,
  },
  creditsPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.background,
  },
  creditsText: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  messagesWrap: {
    flex: 1,
  },
  messages: {
    flex: 1,
  },
  messagesContent: {
    padding: spacing.md,
    gap: spacing.sm,
  },
  floatingButtonWrap: {
    position: 'absolute',
    right: spacing.md,
    bottom: spacing.md,
  },
  pressedDim: {
    opacity: 0.85,
  },
  scrollToBottomButton: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: elevation.raised.shadowColor,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: elevation.raised.shadowOpacity,
    shadowRadius: elevation.raised.shadowRadius,
    elevation: elevation.raised.elevation,
  },
  bubble: {
    maxWidth: '85%',
    borderRadius: radius.xl,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    marginBottom: spacing.sm,
  },
  bubbleAssistant: {
    backgroundColor: colors.surface,
    alignSelf: 'flex-start',
    // A soft "tail" corner (matches the small-radius convention every chat
    // app uses to show which side is speaking) plus a real card shadow
    // instead of a flat 1px border — the single biggest thing that made
    // these bubbles read as unfinished.
    borderBottomLeftRadius: radius.sm,
    shadowColor: elevation.card.shadowColor,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: elevation.card.shadowOpacity,
    shadowRadius: elevation.card.shadowRadius,
    elevation: elevation.card.elevation,
  },
  bubbleUser: {
    alignSelf: 'flex-end',
    borderBottomRightRadius: radius.sm,
  },
  // Deliberately its own size, smaller than the app-wide typography.body
  // (18px, sized for long-form senior-friendly reading elsewhere in the
  // app) — a chat bubble is a short, dense back-and-forth, and at 18px the
  // text was crowding the bubble and reading oversized on an actual phone
  // screen, per direct feedback.
  bubbleText: {
    fontSize: 16,
    lineHeight: 22,
    fontFamily: fontFamily.regular,
    color: colors.textPrimary,
  },
  bubbleTextUser: {
    color: colors.textInverse,
  },
  assistantFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.sm,
  },
  listenButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    alignSelf: 'flex-start',
  },
  listenButtonText: {
    ...typography.caption,
    color: colors.primary,
  },
  answeredByBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  answeredByText: {
    ...typography.caption,
    fontSize: 12,
    lineHeight: 16,
  },
  promptsRow: {
    flexGrow: 0,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surface,
  },
  promptChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: elevation.card.shadowColor,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 1,
  },
  promptChipText: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  micButtonBusy: {
    opacity: 0.6,
  },
  typedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.sm,
    paddingTop: spacing.sm,
    // Extra bottom padding clears the tab bar's popped-up center button
    // (see TAB_BAR_BUTTON_CLEARANCE) — without it this bar sits flush
    // against the screen edge, right where that button protrudes into it.
    paddingBottom: spacing.sm + TAB_BAR_BUTTON_CLEARANCE,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    // A floating-bar shadow cast upward, same convention as
    // VoicePlayerBar's bottom-docked bar — reads as a deliberate composer
    // bar rather than content that just happens to end at the bottom.
    shadowColor: elevation.raised.shadowColor,
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: elevation.raised.shadowOpacity,
    shadowRadius: elevation.raised.shadowRadius,
    elevation: elevation.raised.elevation,
  },
  typedInput: {
    flex: 1,
    ...typography.body,
    color: colors.textPrimary,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    minHeight: minTouchTarget,
    backgroundColor: colors.background,
  },
  composerAction: {
    width: minTouchTarget,
    height: minTouchTarget,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: elevation.card.shadowColor,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: elevation.card.shadowOpacity,
    shadowRadius: elevation.card.shadowRadius,
    elevation: elevation.card.elevation,
  },
});
