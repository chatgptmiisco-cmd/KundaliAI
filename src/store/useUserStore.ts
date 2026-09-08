import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { deleteAccount, invalidateKundaliMemo, putBirthData, restoreAuthToken } from '../api/client';
import { ALL_FEATURES_FREE } from '../config/env';
import { useChatStore } from './useChatStore';
import { useInsightsStore } from './useInsightsStore';
import { useKundaliStore } from './useKundaliStore';
import { AppLanguage, BirthData, PlanTier, PreferenceKey } from '../types/kundali';

const FREE_TRIAL_CREDITS = 3;

// PreferenceKey's values were renamed mid-development (marriage/money/
// education -> family/health/career/marriageRelationships/friends). Anyone
// who picked preferences before that rename still has the OLD strings sitting
// in AsyncStorage, which then crash anything that looks up an icon/label by
// key (e.g. Home's swipeable focus tabs). The version bump below forces
// `migrate` to run once for every existing install and drop anything that
// isn't a current, valid key.
const VALID_PREFERENCE_KEYS: PreferenceKey[] = ['family', 'health', 'career', 'marriageRelationships', 'friends'];

interface UserState {
  language: AppLanguage;
  plan: PlanTier;
  birthData: BirthData;
  isPremium: boolean;
  hasOnboarded: boolean;
  credits: number;
  preferences: PreferenceKey[];
  accuracyScore: number | null;
  authToken: string | null;
  email: string | null;
  setLanguage: (lang: AppLanguage) => void;
  setPlan: (plan: PlanTier) => void;
  setBirthData: (data: BirthData) => Promise<void>;
  setPreferences: (prefs: PreferenceKey[]) => void;
  setAccuracyScore: (score: number) => void;
  setAuthSession: (token: string, email: string) => void;
  finishOnboarding: () => void;
  resetOnboarding: () => Promise<void>;
  logOut: () => void;
  addCredits: (amount: number) => void;
  spendCredit: () => boolean;
}

const defaultBirthData: BirthData = {
  name: '',
  dateOfBirth: '',
  timeOfBirth: '',
  placeOfBirth: '',
};

export const useUserStore = create<UserState>()(
  persist(
    (set, get) => ({
      language: 'en',
      plan: 'free',
      birthData: defaultBirthData,
      isPremium: ALL_FEATURES_FREE,
      hasOnboarded: false,
      credits: FREE_TRIAL_CREDITS,
      preferences: [],
      accuracyScore: null,
      authToken: null,
      email: null,

      setLanguage: (language) => set({ language }),
      setPlan: (plan) => set({ plan, isPremium: ALL_FEATURES_FREE || plan !== 'free' }),

      setBirthData: async (birthData) => {
        await putBirthData(birthData);
        set({ birthData });
        invalidateKundaliMemo();
        useKundaliStore.getState().invalidateAll();
      },

      setPreferences: (preferences) => set({ preferences }),
      setAccuracyScore: (accuracyScore) => set({ accuracyScore }),

      setAuthSession: (authToken, email) => {
        restoreAuthToken(authToken);
        set({ authToken, email });
      },

      finishOnboarding: () => set({ hasOnboarded: true }),

      resetOnboarding: async () => {
        try {
          await deleteAccount();
        } catch {
          // best-effort — token may already be invalid/expired, fine to ignore
        }
        restoreAuthToken(null);
        set({
          hasOnboarded: false,
          birthData: defaultBirthData,
          preferences: [],
          accuracyScore: null,
          credits: FREE_TRIAL_CREDITS,
          authToken: null,
          email: null,
          plan: 'free',
          isPremium: ALL_FEATURES_FREE,
        });
        useKundaliStore.getState().invalidateAll();
        useInsightsStore.getState().reset();
        useChatStore.getState().reset();
      },

      /** Signs the user out of this device only — the account and its data
       * stay intact server-side (unlike resetOnboarding, which deletes the
       * account). Clears local session/profile state so a different user can
       * sign in on the same device without seeing the previous user's data. */
      logOut: () => {
        restoreAuthToken(null);
        set({
          hasOnboarded: false,
          birthData: defaultBirthData,
          preferences: [],
          accuracyScore: null,
          credits: FREE_TRIAL_CREDITS,
          authToken: null,
          email: null,
          plan: 'free',
          isPremium: ALL_FEATURES_FREE,
        });
        useKundaliStore.getState().invalidateAll();
        useInsightsStore.getState().reset();
        useChatStore.getState().reset();
      },

      addCredits: (amount) => set((state) => ({ credits: state.credits + amount })),

      spendCredit: () => {
        const { credits, isPremium } = get();
        if (isPremium) return true;
        if (credits <= 0) return false;
        set({ credits: credits - 1 });
        return true;
      },
    }),
    {
      name: 'kundaliai-user-store',
      storage: createJSONStorage(() => AsyncStorage),
      version: 1,
      migrate: (persisted: any) => {
        if (persisted && Array.isArray(persisted.preferences)) {
          persisted.preferences = persisted.preferences.filter((p: string) =>
            VALID_PREFERENCE_KEYS.includes(p as PreferenceKey),
          );
        }
        return persisted;
      },
      onRehydrateStorage: () => (state) => {
        // The http client's auth token lives in a module-level variable, not
        // in this persisted store — restore it once rehydration completes.
        if (state?.authToken) restoreAuthToken(state.authToken);
      },
    },
  ),
);
