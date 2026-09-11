import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React from 'react';
import RishiChatScreen from '../screens/RishiChatScreen';
import { RishiStackParamList } from './types';

const Stack = createNativeStackNavigator<RishiStackParamList>();

// Chat is the only screen here now — no separate Rishi-picker step. Its
// header is fully custom (portrait + name + switcher, see RishiChatScreen),
// so the native stack header is hidden rather than showing an empty bar
// above it.
export default function RishiStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="RishiChat" component={RishiChatScreen} />
    </Stack.Navigator>
  );
}
