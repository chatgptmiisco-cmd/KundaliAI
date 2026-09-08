import { create } from 'zustand';
import {
  getChart,
  getDashaTimeline,
  getKundaliSummary,
  getManglikStatus,
  getValidationQuestions,
  postKundaliComplete,
} from '../api/client';
import {
  BirthChart,
  ChartType,
  DashaPeriod,
  KundaliComplete,
  KundaliSummary,
  Language,
  ManglikStatus,
  ValidationQuestion,
} from '../types/kundali';

interface CacheEntry<T> {
  [language: string]: T;
}

interface ChartCacheEntry {
  [type: string]: CacheEntry<BirthChart>;
}

interface KundaliState {
  summary: CacheEntry<KundaliSummary>;
  complete: CacheEntry<KundaliComplete>;
  manglik: CacheEntry<ManglikStatus>;
  charts: ChartCacheEntry;
  dasha: CacheEntry<DashaPeriod[]>;
  validationQuestions: CacheEntry<ValidationQuestion[]>;

  summaryLoading: boolean;
  completeLoading: boolean;
  manglikLoading: boolean;
  chartLoading: boolean;
  dashaLoading: boolean;
  validationQuestionsLoading: boolean;

  summaryError: boolean;
  completeError: boolean;
  manglikError: boolean;
  chartError: boolean;
  dashaError: boolean;
  validationQuestionsError: boolean;

  fetchSummary: (lang: Language) => Promise<void>;
  fetchManglik: (lang: Language) => Promise<void>;
  fetchComplete: (lang: Language) => Promise<void>;
  fetchChart: (type: ChartType, lang: Language) => Promise<void>;
  fetchDasha: (lang: Language, birthDateIso: string) => Promise<void>;
  fetchValidationQuestions: (lang: Language) => Promise<void>;

  /** Call when birth data changes to drop all cached reports. */
  invalidateAll: () => void;
}

export const useKundaliStore = create<KundaliState>((set, get) => ({
  summary: {},
  complete: {},
  manglik: {},
  charts: {},
  dasha: {},
  validationQuestions: {},

  summaryLoading: false,
  completeLoading: false,
  manglikLoading: false,
  chartLoading: false,
  dashaLoading: false,
  validationQuestionsLoading: false,

  summaryError: false,
  completeError: false,
  manglikError: false,
  chartError: false,
  dashaError: false,
  validationQuestionsError: false,

  fetchSummary: async (lang) => {
    if (get().summary[lang]) return;
    set({ summaryLoading: true, summaryError: false });
    try {
      const data = await getKundaliSummary(lang);
      set((state) => ({ summary: { ...state.summary, [lang]: data }, summaryLoading: false }));
    } catch {
      set({ summaryLoading: false, summaryError: true });
    }
  },

  fetchManglik: async (lang) => {
    if (get().manglik[lang]) return;
    set({ manglikLoading: true, manglikError: false });
    try {
      const data = await getManglikStatus(lang);
      set((state) => ({ manglik: { ...state.manglik, [lang]: data }, manglikLoading: false }));
    } catch {
      set({ manglikLoading: false, manglikError: true });
    }
  },

  fetchComplete: async (lang) => {
    if (get().complete[lang]) return;
    set({ completeLoading: true, completeError: false });
    try {
      const data = await postKundaliComplete(lang);
      set((state) => ({ complete: { ...state.complete, [lang]: data }, completeLoading: false }));
    } catch {
      set({ completeLoading: false, completeError: true });
    }
  },

  fetchChart: async (type, lang) => {
    if (get().charts[type]?.[lang]) return;
    set({ chartLoading: true, chartError: false });
    try {
      const data = await getChart(type, lang);
      set((state) => ({
        charts: { ...state.charts, [type]: { ...state.charts[type], [lang]: data } },
        chartLoading: false,
      }));
    } catch {
      set({ chartLoading: false, chartError: true });
    }
  },

  fetchDasha: async (lang, birthDateIso) => {
    if (get().dasha[lang]) return;
    set({ dashaLoading: true, dashaError: false });
    try {
      const data = await getDashaTimeline(lang, birthDateIso);
      set((state) => ({ dasha: { ...state.dasha, [lang]: data }, dashaLoading: false }));
    } catch {
      set({ dashaLoading: false, dashaError: true });
    }
  },

  fetchValidationQuestions: async (lang) => {
    if (get().validationQuestions[lang]) return;
    set({ validationQuestionsLoading: true, validationQuestionsError: false });
    try {
      const data = await getValidationQuestions(lang);
      set((state) => ({
        validationQuestions: { ...state.validationQuestions, [lang]: data },
        validationQuestionsLoading: false,
      }));
    } catch {
      set({ validationQuestionsLoading: false, validationQuestionsError: true });
    }
  },

  invalidateAll: () =>
    set({ summary: {}, complete: {}, manglik: {}, charts: {}, dasha: {}, validationQuestions: {} }),
}));
