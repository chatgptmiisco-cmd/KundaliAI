import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { ChatMessage } from '../types/kundali';

interface ChatState {
  messagesByRishi: Record<string, ChatMessage[]>;
  initConversation: (rishiId: string, greeting: string) => void;
  addMessage: (rishiId: string, message: ChatMessage) => void;
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

      reset: () => set({ messagesByRishi: {} }),
    }),
    {
      name: 'kundaliai-chat-store',
      storage: createJSONStorage(() => AsyncStorage),
      version: 1,
    },
  ),
);
