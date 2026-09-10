import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React, { useEffect, useState } from 'react';
import i18n from '../i18n/i18n';
import { useTranslation } from 'react-i18next';
import AiProcessingScreen from '../screens/AiProcessingScreen';
import AppInfoScreen from '../screens/AppInfoScreen';
import AuthScreen from '../screens/AuthScreen';
import BirthDataScreen from '../screens/BirthDataScreen';
import GunaMilanScreen from '../screens/GunaMilanScreen';
import HoroscopeDetailScreen from '../screens/HoroscopeDetailScreen';
import InsightsScreen from '../screens/InsightsScreen';
import ManglikAnalysisScreen from '../screens/ManglikAnalysisScreen';
import PassStoreScreen from '../screens/PassStoreScreen';
import PaymentScreen from '../screens/PaymentScreen';
import PeriodAnalysisScreen from '../screens/PeriodAnalysisScreen';
import PredictionsScreen from '../screens/PredictionsScreen';
import PreferencesScreen from '../screens/PreferencesScreen';
import SplashScreen from '../screens/SplashScreen';
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

  if (!timerDone || !hydrated) {
    return <SplashScreen />;
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
            name="Predictions"
            component={PredictionsScreen}
            options={{ title: t('predictions.screenTitle') }}
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
        </>
      )}
    </Stack.Navigator>
  );
}
