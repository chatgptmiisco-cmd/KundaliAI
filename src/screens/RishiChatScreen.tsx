import { Ionicons } from '@expo/vector-icons';
import { useNavigation, useRoute } from '@react-navigation/native';
import React, { useEffect, useRef, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { postChatMessage } from '../api/client';
import PremiumModal from '../components/PremiumModal';
import { ALL_FEATURES_FREE } from '../config/env';
import { findRishi } from '../constants/rishis';
import { getRishiReply } from '../data/chatReplies';
import { toContentLanguage } from '../i18n/contentLanguage';
import { useChatStore } from '../store/useChatStore';
import { useUserStore } from '../store/useUserStore';
import { useVoiceStore } from '../store/useVoiceStore';
import { colors, elevation, fontFamily, minTouchTarget, radius, spacing, typography } from '../theme/theme';

type Phase = 'idle' | 'thinking';

export default function RishiChatScreen() {
  const { t } = useTranslation();
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const rishi = findRishi(route.params?.rishiId);

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
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    navigation.setOptions({ title: rishi.name });
    initConversation(rishi.id, t(`rishiPicker.${rishi.id}.greeting`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rishi.id]);

  const sendToAssistant = async (text: string) => {
    if (!text.trim()) return;

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
    if (hasStrategyAccess) {
      setPhase('thinking');
      try {
        reply = await postChatMessage(text, contentLanguage, rishi.id);
      } catch {
        const assistantIndex = messages.filter((m) => m.role === 'assistant').length;
        reply = getRishiReply(rishi.tone, assistantIndex, contentLanguage);
      }
    } else {
      const assistantIndex = messages.filter((m) => m.role === 'assistant').length;
      reply = getRishiReply(rishi.tone, assistantIndex, contentLanguage);
    }

    addMessage(rishi.id, { id: `a-${Date.now()}`, role: 'assistant', text: reply, createdAt: Date.now() });
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

  const quickPrompts = [t('rishi.promptWeek'), t('rishi.promptDasha'), t('rishi.promptCareer'), t('rishi.promptRemedy')];
  const micLabel = phase === 'thinking' ? t('voiceChat.thinking') : t('voiceChat.tapToAsk');
  const micBusy = phase === 'thinking';

  return (
    <View style={styles.screen}>
      <View style={styles.rishiHeader}>
        <View style={[styles.portrait, { backgroundColor: rishi.gradient[1] }]}>
          <Text style={styles.portraitText}>{rishi.initial}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.rishiName}>{rishi.name}</Text>
          <Text style={styles.rishiFocus}>{t(`rishiPicker.${rishi.id}.focus`)}</Text>
        </View>
        <View style={styles.creditsPill}>
          <Ionicons name="diamond-outline" size={13} color={colors.primary} />
          <Text style={styles.creditsText}>
            {isPremium ? t('rishi.unlimitedMessages') : t('rishi.freeMessagesLeft', { count: credits })}
          </Text>
        </View>
      </View>

      <ScrollView
        ref={scrollRef}
        style={styles.messages}
        contentContainerStyle={styles.messagesContent}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
      >
        {messages.map((m) => (
          <View
            key={m.id}
            style={[styles.bubble, m.role === 'user' ? styles.bubbleUser : styles.bubbleAssistant]}
          >
            <Text style={[styles.bubbleText, m.role === 'user' && styles.bubbleTextUser]}>{m.text}</Text>
            {m.role === 'assistant' && (
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
            )}
          </View>
        ))}
      </ScrollView>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.promptsRow} contentContainerStyle={{ gap: spacing.xs, paddingHorizontal: spacing.md }}>
        {quickPrompts.map((p) => (
          <Pressable key={p} onPress={() => sendToAssistant(p)} style={styles.promptChip}>
            <Text style={styles.promptChipText}>{p}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <View style={styles.micArea}>
        <Pressable
          onPress={handleMicPress}
          disabled={micBusy}
          accessibilityRole="button"
          accessibilityLabel={micLabel}
          style={[styles.micButton, { backgroundColor: rishi.gradient[1] }, micBusy && styles.micButtonBusy]}
        >
          <Ionicons name="mic" size={40} color={colors.textInverse} />
        </Pressable>
        <Text style={styles.micLabel}>{micLabel}</Text>
      </View>

      <View style={styles.typedRow}>
        <TextInput
          value={typedInput}
          onChangeText={setTypedInput}
          placeholder={t('voiceChat.typeInsteadPlaceholder')}
          placeholderTextColor={colors.textSecondary}
          style={styles.typedInput}
          onSubmitEditing={handleSendTyped}
        />
        <Pressable
          onPress={handleSendTyped}
          accessibilityRole="button"
          accessibilityLabel={t('rishi.send')}
          style={[styles.typedSend, { backgroundColor: rishi.gradient[1] }]}
        >
          <Ionicons name="arrow-up" size={20} color={colors.textInverse} />
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
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  portrait: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  portraitText: {
    fontSize: 18,
    fontFamily: fontFamily.displayBold,
    color: colors.textInverse,
  },
  rishiName: {
    ...typography.bodyBold,
    color: colors.textPrimary,
  },
  rishiFocus: {
    ...typography.caption,
    color: colors.textSecondary,
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
  messages: {
    flex: 1,
  },
  messagesContent: {
    padding: spacing.md,
    gap: spacing.sm,
  },
  bubble: {
    maxWidth: '85%',
    borderRadius: radius.lg,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  bubbleAssistant: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignSelf: 'flex-start',
  },
  bubbleUser: {
    backgroundColor: colors.primary,
    alignSelf: 'flex-end',
  },
  bubbleText: {
    ...typography.body,
    color: colors.textPrimary,
  },
  bubbleTextUser: {
    color: colors.textInverse,
  },
  listenButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: spacing.xs,
    alignSelf: 'flex-start',
  },
  listenButtonText: {
    ...typography.caption,
    color: colors.primary,
  },
  promptsRow: {
    flexGrow: 0,
    paddingVertical: spacing.xs,
    backgroundColor: colors.surface,
  },
  promptChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.border,
  },
  promptChipText: {
    ...typography.caption,
    color: colors.textSecondary,
  },
  micArea: {
    alignItems: 'center',
    paddingVertical: spacing.md,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  micButton: {
    width: 84,
    height: 84,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: elevation.raised.shadowColor,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: elevation.raised.shadowOpacity,
    shadowRadius: elevation.raised.shadowRadius,
    elevation: elevation.raised.elevation,
  },
  micButtonBusy: {
    opacity: 0.6,
  },
  micLabel: {
    ...typography.caption,
    color: colors.textSecondary,
    marginTop: spacing.sm,
  },
  typedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.sm,
    backgroundColor: colors.surface,
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
  typedSend: {
    width: minTouchTarget,
    height: minTouchTarget,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
