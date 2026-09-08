import { create } from 'zustand';
import { buildInsights } from '../data/insights';
import { Insight, KundaliSummary, Language, PreferenceKey } from '../types/kundali';

interface InsightsState {
  insights: Insight[];
  unreadCount: number;
  generate: (preferences: PreferenceKey[], language: Language, summary: KundaliSummary) => void;
  markAllRead: () => void;
  reset: () => void;
}

export const useInsightsStore = create<InsightsState>((set, get) => ({
  insights: [],
  unreadCount: 0,

  generate: (preferences, language, summary) => {
    if (get().insights.length > 0 || preferences.length === 0) return;
    const insights = buildInsights(preferences, language, summary);
    set({ insights, unreadCount: insights.length });
  },

  markAllRead: () => set({ unreadCount: 0 }),
  reset: () => set({ insights: [], unreadCount: 0 }),
}));
