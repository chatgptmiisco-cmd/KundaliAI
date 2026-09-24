import { createNativeStackNavigator } from '@react-navigation/native-stack';
import * as Updates from 'expo-updates';
import React, { useEffect, useState } from 'react';
import i18n from '../i18n/i18n';
import { useTranslation } from 'react-i18next';
import AiProcessingScreen from '../screens/AiProcessingScreen';
import AppInfoScreen from '../screens/AppInfoScreen';
import AuthScreen from '../screens/AuthScreen';
import BirthDataScreen from '../screens/BirthDataScreen';
import ChartLookupScreen from '../screens/ChartLookupScreen';
import FollowUpQuestionsScreen from '../screens/FollowUpQuestionsScreen';
import GunaMilanScreen from '../screens/GunaMilanScreen';
import HoroscopeDetailScreen from '../screens/HoroscopeDetailScreen';
import InsightsScreen from '../screens/InsightsScreen';
import LifeTimelineScreen from '../screens/LifeTimelineScreen';
import ManglikAnalysisScreen from '../screens/ManglikAnalysisScreen';
import MyLifeTwinScreen from '../screens/MyLifeTwinScreen';
import PassStoreScreen from '../screens/PassStoreScreen';
import PaymentScreen from '../screens/PaymentScreen';
import PeriodAnalysisScreen from '../screens/PeriodAnalysisScreen';
import PreferencesScreen from '../screens/PreferencesScreen';
import SplashScreen from '../screens/SplashScreen';
import TopicFollowUpScreen from '../screens/TopicFollowUpScreen';
import TopicSelectionScreen from '../screens/TopicSelectionScreen';
import UpgradePlansScreen from '../screens/UpgradePlansScreen';
import ValidationScreen from '../screens/ValidationScreen';
import WelcomeScreen from '../screens/WelcomeScreen';
import { useUserStore } from '../store/useUserStore';
import { colors, fontFamily } from '../theme/theme';
import MainTabs from './MainTabs';
import { RootStackParamList } from './types';

const Stack = createNativeStackNavigator<RootStackParamList>();
const MIN_SPLASH_MS = 800;

export default function RootNavigator() {
  const { t } = useTranslation();
  const hasOnboarded = useUserStore((s) => s.hasOnboarded);

  const [timerDone, setTimerDone] = useState(false);
  const [hydrated, setHydrated] = useState(useUserStore.persist.hasHydrated());
  const [updateChecked, setUpdateChecked] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setTimerDone(true), MIN_SPLASH_MS);
    const unsub = useUserStore.persist.onFinishHydration(() => setHydrated(true));
    return () => {
      clearTimeout(timer);
      unsub();
    };
  }, []);

  useEffect(() => {
    if (hydrated) {
      i18n.changeLanguage(useUserStore.getState().language);
    }
  }, [hydrated]);

  // OTA update check — runs once on boot, alongside the min-splash timer
  // and store hydration above. `Updates.isEnabled` is false in Expo Go and
  // any dev/development-client build (no channel to check against), so
  // this is a silent no-op there instead of the "not supported in
  // development" throw checkForUpdateAsync would otherwise raise.
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (!Updates.isEnabled) {
        if (!cancelled) setUpdateChecked(true);
        return;
      }
      try {
        setUpdateStatus(i18n.t('common.checkingForUpdates'));
        const update = await Updates.checkForUpdateAsync();
        if (cancelled) return;
        if (update.isAvailable) {
          setUpdateStatus(i18n.t('common.downloadingUpdate'));
          await Updates.fetchUpdateAsync();
          if (cancelled) return;
          setUpdateStatus(i18n.t('common.updateReadyRestarting'));
          await Updates.reloadAsync();
          return; // App reloads — nothing left to update in this instance.
        }
      } catch (updateError) {
        console.log('Update check failed:', updateError);
      }
      if (!cancelled) {
        setUpdateStatus(null);
        setUpdateChecked(true);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!timerDone || !hydrated || !updateChecked) {
    return <SplashScreen statusText={updateStatus} />;
  }

  return (
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.surface },
        headerTitleStyle: { fontFamily: fontFamily.semiBold, fontSize: 20, color: colors.textPrimary },
        headerTintColor: colors.primary,
        headerBackTitle: t('common.back') ?? undefined,
        contentStyle: { backgroundColor: colors.background },
      }}
    >
      {!hasOnboarded ? (
        <>
          <Stack.Screen name="Welcome" component={WelcomeScreen} options={{ headerShown: false }} />
          <Stack.Screen name="AppInfo" component={AppInfoScreen} options={{ headerShown: false }} />
          <Stack.Screen
            name="Auth"
            component={AuthScreen}
            options={{ title: t('onboarding.authTitle') }}
          />
          <Stack.Screen
            name="BirthData"
            component={BirthDataScreen}
            options={{ title: t('onboarding.birthDataTitle') }}
          />
          <Stack.Screen
            name="TopicSelection"
            component={TopicSelectionScreen}
            options={{ title: t('onboardingTopics.title'), headerBackVisible: false, gestureEnabled: false }}
          />
          <Stack.Screen
            name="TopicFollowUp"
            component={TopicFollowUpScreen}
            options={{ title: t('onboardingTopics.title') }}
          />
          <Stack.Screen
            name="AiProcessing"
            component={AiProcessingScreen}
            options={{ headerShown: false, gestureEnabled: false }}
          />
          <Stack.Screen
            name="Validation"
            component={ValidationScreen}
            options={{ title: t('validation.title'), headerBackVisible: false, gestureEnabled: false }}
          />
          <Stack.Screen
            name="Preferences"
            component={PreferencesScreen}
            options={{ title: t('preferences.title'), headerBackVisible: false, gestureEnabled: false }}
          />
        </>
      ) : (
        <>
          <Stack.Screen name="MainTabs" component={MainTabs} options={{ headerShown: false }} />
          <Stack.Screen
            name="ManglikAnalysis"
            component={ManglikAnalysisScreen}
            options={{ title: t('manglik.screenTitle') }}
          />
          <Stack.Screen
            name="UpgradePlans"
            component={UpgradePlansScreen}
            options={{ title: t('plans.screenTitle') }}
          />
          <Stack.Screen
            name="PeriodAnalysis"
            component={PeriodAnalysisScreen}
            options={{ title: t('periods.screenTitle') }}
          />
          <Stack.Screen
            name="HoroscopeDetail"
            component={HoroscopeDetailScreen}
            options={{ title: t('horoscope.screenTitle') }}
          />
          <Stack.Screen
            name="GunaMilan"
            component={GunaMilanScreen}
            options={{ title: t('gunaMilan.screenTitle') }}
          />
          <Stack.Screen
            name="PassStore"
            component={PassStoreScreen}
            options={{ title: t('passStore.screenTitle') }}
          />
          <Stack.Screen
            name="Payment"
            component={PaymentScreen}
            options={{ title: t('payment.screenTitle') }}
          />
          <Stack.Screen
            name="Insights"
            component={InsightsScreen}
            options={{ title: t('insights.screenTitle') }}
          />
          <Stack.Screen
            name="MyLifeTwin"
            component={MyLifeTwinScreen}
            options={{ title: t('lifeTwin.screenTitle') }}
          />
          <Stack.Screen
            name="LifeTimeline"
            component={LifeTimelineScreen}
            options={{ title: t('lifeTimeline.screenTitle') }}
          />
          <Stack.Screen
            name="ChartLookup"
            component={ChartLookupScreen}
            options={{ title: t('chartLookup.screenTitle') }}
          />
          <Stack.Screen
            name="FollowUpQuestions"
            component={FollowUpQuestionsScreen}
            options={{ title: t('followUp.screenTitle') }}
          />
        </>
      )}
    </Stack.Navigator>
  );
}
