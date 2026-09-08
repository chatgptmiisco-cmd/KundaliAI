import { create } from 'zustand';
import { ChatMessage } from '../types/kundali';

interface ChatState {
  messagesByRishi: Record<string, ChatMessage[]>;
  initConversation: (rishiId: string, greeting: string) => void;
  addMessage: (rishiId: string, message: ChatMessage) => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
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
}));
