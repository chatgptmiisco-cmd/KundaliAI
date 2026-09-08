import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React from 'react';
import { useTranslation } from 'react-i18next';
import RishiChatScreen from '../screens/RishiChatScreen';
import RishiPickerScreen from '../screens/RishiPickerScreen';
import { colors, fontFamily } from '../theme/theme';
import { RishiStackParamList } from './types';

const Stack = createNativeStackNavigator<RishiStackParamList>();

export default function RishiStack() {
  const { t } = useTranslation();

  return (
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.surface },
        headerTitleStyle: { fontFamily: fontFamily.semiBold, fontSize: 20, color: colors.textPrimary },
        headerTintColor: colors.primary,
        headerBackTitle: t('common.back') ?? undefined,
      }}
    >
      <Stack.Screen name="RishiPicker" component={RishiPickerScreen} options={{ headerShown: false }} />
      <Stack.Screen name="RishiChat" component={RishiChatScreen} options={{ title: '' }} />
    </Stack.Navigator>
  );
}
