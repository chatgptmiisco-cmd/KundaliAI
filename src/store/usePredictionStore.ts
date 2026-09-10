import { create } from 'zustand';
import { getMarriageTimingPrediction, getMultiYearOutlook, getYearAheadOutlook } from '../api/client';
import { Language, MarriageTimingPrediction, YearOutlook } from '../types/kundali';

interface CacheEntry<T> {
  [language: string]: T;
}

interface YearCacheEntry {
  [year: number]: CacheEntry<YearOutlook>;
}

interface MultiYearCacheEntry {
  [years: number]: CacheEntry<YearOutlook[]>;
}

interface PredictionState {
  yearOutlooks: YearCacheEntry;
  multiYearOutlooks: MultiYearCacheEntry;
  marriageTiming: CacheEntry<MarriageTimingPrediction>;

  yearOutlookLoading: boolean;
  multiYearOutlookLoading: boolean;
  marriageTimingLoading: boolean;

  yearOutlookError: boolean;
  multiYearOutlookError: boolean;
  marriageTimingError: boolean;

  fetchYearOutlook: (lang: Language, year: number) => Promise<void>;
  fetchMultiYearOutlook: (lang: Language, years: number) => Promise<void>;
  fetchMarriageTiming: (lang: Language) => Promise<void>;

  /** Call when birth data changes to drop all cached predictions. */
  invalidateAll: () => void;
}

export const usePredictionStore = create<PredictionState>((set, get) => ({
  yearOutlooks: {},
  multiYearOutlooks: {},
  marriageTiming: {},

  yearOutlookLoading: false,
  multiYearOutlookLoading: false,
  marriageTimingLoading: false,

  yearOutlookError: false,
  multiYearOutlookError: false,
  marriageTimingError: false,

  fetchYearOutlook: async (lang, year) => {
    if (get().yearOutlooks[year]?.[lang]) return;
    set({ yearOutlookLoading: true, yearOutlookError: false });
    try {
      const data = await getYearAheadOutlook(lang, year);
      set((state) => ({
        yearOutlooks: { ...state.yearOutlooks, [year]: { ...state.yearOutlooks[year], [lang]: data } },
        yearOutlookLoading: false,
      }));
    } catch {
      set({ yearOutlookLoading: false, yearOutlookError: true });
    }
  },

  fetchMultiYearOutlook: async (lang, years) => {
    if (get().multiYearOutlooks[years]?.[lang]) return;
    set({ multiYearOutlookLoading: true, multiYearOutlookError: false });
    try {
      const data = await getMultiYearOutlook(lang, years);
      set((state) => ({
        multiYearOutlooks: { ...state.multiYearOutlooks, [years]: { ...state.multiYearOutlooks[years], [lang]: data } },
        multiYearOutlookLoading: false,
      }));
    } catch {
      set({ multiYearOutlookLoading: false, multiYearOutlookError: true });
    }
  },

  fetchMarriageTiming: async (lang) => {
    if (get().marriageTiming[lang]) return;
    set({ marriageTimingLoading: true, marriageTimingError: false });
    try {
      const data = await getMarriageTimingPrediction(lang);
      set((state) => ({ marriageTiming: { ...state.marriageTiming, [lang]: data }, marriageTimingLoading: false }));
    } catch {
      set({ marriageTimingLoading: false, marriageTimingError: true });
    }
  },

  invalidateAll: () => set({ yearOutlooks: {}, multiYearOutlooks: {}, marriageTiming: {} }),
}));
