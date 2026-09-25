import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { ChatMessage } from '../types/kundali';

interface ChatState {
  messagesByRishi: Record<string, ChatMessage[]>;
  initConversation: (rishiId: string, greeting: string) => void;
  addMessage: (rishiId: string, message: ChatMessage) => void;
  hydrateHistory: (rishiId: string, messages: ChatMessage[]) => void;
  reset: () => void;
}

// Persisted to AsyncStorage (same pattern as useUserStore) — conversations
// used to live only in memory, so force-closing the app or navigating away
// and back lost every prior message. useUserStore.logOut/resetOnboarding
// already call reset() on this store, so persistence doesn't leak a
// previous user's chat history onto the next login on the same device.
export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      messagesByRishi: {},

      initConversation: (rishiId, greeting) => {
        if (get().messagesByRishi[rishiId]) return;
        set((state) => ({
          messagesByRishi: {
            ...state.messagesByRishi,
            [rishiId]: [
              { id: `${rishiId}-greeting`, role: 'assistant', text: greeting, createdAt: Date.now() },
            ],
          },
        }));
      },

      addMessage: (rishiId, message) => {
        set((state) => ({
          messagesByRishi: {
            ...state.messagesByRishi,
            [rishiId]: [...(state.messagesByRishi[rishiId] ?? []), message],
          },
        }));
      },

      // The server's own chat_messages table (see api/client.ts's
      // getChatHistory) is the real, shared source of truth across devices
      // — this replaces whatever this one device's local cache had for the
      // Rishi with what the server actually has, so a phone and a browser
      // signed into the same account converge on the SAME conversation
      // instead of each keeping its own local-only copy. A no-op when the
      // server has nothing yet (a brand-new conversation) — initConversation's
      // locally-seeded greeting is left standing rather than wiped to empty.
      hydrateHistory: (rishiId, messages) => {
        if (messages.length === 0) return;
        set((state) => ({
          messagesByRishi: { ...state.messagesByRishi, [rishiId]: messages },
        }));
      },

      reset: () => set({ messagesByRishi: {} }),
    }),
    {
      name: 'kundaliai-chat-store',
      storage: createJSONStorage(() => AsyncStorage),
      version: 1,
    },
  ),
);
