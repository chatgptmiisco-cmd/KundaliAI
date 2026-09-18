import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { deleteAccount, invalidateKundaliMemo, putBirthData, putPreferences, restoreAuthToken } from '../api/client';
import { setSessionExpiredHandler } from '../api/httpClient';
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

export type ChartStyle = 'north' | 'south';

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
  chartStyle: ChartStyle;
  setLanguage: (lang: AppLanguage) => void;
  setPlan: (plan: PlanTier) => void;
  setChartStyle: (style: ChartStyle) => void;
  setBirthData: (data: BirthData) => Promise<void>;
  hydrateBirthData: (data: BirthData) => void;
  hydrateAccountName: (name: string) => void;
  setPreferences: (prefs: PreferenceKey[]) => Promise<void>;
  hydratePreferences: (prefs: PreferenceKey[]) => void;
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
      chartStyle: 'north',

      setLanguage: (language) => set({ language }),
      setPlan: (plan) => set({ plan, isPremium: ALL_FEATURES_FREE || plan !== 'free' }),
      setChartStyle: (chartStyle) => set({ chartStyle }),

      setBirthData: async (birthData) => {
        await putBirthData(birthData);
        set({ birthData });
        invalidateKundaliMemo();
        useKundaliStore.getState().invalidateAll();
      },

      // Unlike setBirthData, this does NOT re-PUT to the server — it's for
      // hydrating local state from a profile that ALREADY has birth data
      // saved server-side (a returning user logging in on a new device),
      // so it doesn't needlessly bump birth_profile_version and invalidate
      // every chart/reading cache that's already correctly computed.
      hydrateBirthData: (birthData) => set({ birthData }),

      // The account holder's name was just typed on the signup form —
      // carrying it into the (still-empty) birthData draft here means the
      // very next screen (BirthDataScreen) doesn't have to ask for it a
      // second time. Only touches `name`; dateOfBirth/timeOfBirth/
      // placeOfBirth stay whatever they already were (empty, pre-onboarding).
      hydrateAccountName: (name) => set((state) => ({ birthData: { ...state.birthData, name } })),

      setPreferences: async (preferences) => {
        set({ preferences });
        // Best-effort — a failed save shouldn't block the local UI update;
        // the next successful save (or the server round-trip on a future
        // login) reconciles it. Preferences aren't safety-critical the way
        // birth data is, so this doesn't need setBirthData's stricter
        // await-then-commit ordering.
        try {
          await putPreferences(preferences);
        } catch {
          // ignore — see above
        }
      },

      // Unlike setPreferences, this does NOT re-PUT to the server — for
      // hydrating local state from a profile that already has preferences
      // saved server-side (a returning user logging in on a new device).
      hydratePreferences: (preferences) => set({ preferences }),
      setAccuracyScore: (accuracyScore) => set({ accuracyScore }),

      // Always starts from a clean onboarding state — without this, a stale
      // `hasOnboarded: true` left over from a PREVIOUS account on this same
      // device/browser (e.g. after the backend database was reset, orphaning
      // the old account) would make a brand-new signup jump straight to
      // Home instead of through BirthData/Validation. The real "returning
      // user with existing data" fast-path still works correctly — it's
      // decided right after this by resumeExistingAccountOrGoToBirthData,
      // based on what the SERVER actually has for this account, not by
      // trusting whatever was cached locally before.
      setAuthSession: (authToken, email) => {
        restoreAuthToken(authToken);
        set({
          authToken,
          email,
          hasOnboarded: false,
          birthData: defaultBirthData,
          preferences: [],
          accuracyScore: null,
        });
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

// A token can go dead without the app ever calling logOut() itself — e.g. the
// backend database was reset (as happens routinely in dev) and now points at
// no account at all. Without this, the device stays stuck believing it's
// logged in and onboarded while every real request 401s silently.
setSessionExpiredHandler(() => useUserStore.getState().logOut());
