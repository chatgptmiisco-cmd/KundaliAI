import { Ionicons } from '@expo/vector-icons';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import React from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';
import { BottomTabBarButtonProps } from '@react-navigation/bottom-tabs';
import { useTranslation } from 'react-i18next';
import ChartsScreen from '../screens/ChartsScreen';
import CompleteKundaliScreen from '../screens/CompleteKundaliScreen';
import HomeDashboardScreen from '../screens/HomeDashboardScreen';
import ProfileScreen from '../screens/ProfileScreen';
import WebSidebarNav from '../components/WebSidebarNav';
import { colors, elevation, fontFamily, radius } from '../theme/theme';
import RishiStack from './RishiStack';
import { MainTabParamList } from './types';

const Tab = createBottomTabNavigator<MainTabParamList>();

// The center "Ask a Rishi" tab gets a big, elevated circular button instead
// of the standard small icon+label — it reads as the app's primary
// interaction, not just another tab.
function CenterMicButton({ children, onPress, accessibilityState }: BottomTabBarButtonProps) {
  const focused = accessibilityState?.selected;
  return (
    <View style={styles.centerButtonWrap} pointerEvents="box-none">
      <Pressable
        onPress={onPress}
        accessibilityRole="button"
        style={[styles.centerButton, focused && styles.centerButtonActive]}
      >
        {children}
      </Pressable>
    </View>
  );
}

export default function MainTabs() {
  const { t } = useTranslation();

  return (
    <Tab.Navigator
      // Desktop gets a persistent left sidebar instead of a bottom bar (see
      // WebSidebarNav) — native is completely untouched, still the default
      // bottom tab bar built from screenOptions/options below exactly as
      // before. One navigator, one set of Tab.Screen registrations either
      // way; this only swaps which component renders the chrome around them.
      // tabBarPosition:'left' is what actually makes the navigator lay the
      // bar out as a true side-by-side sidebar (a real, first-class option
      // on this navigator — it switches its own root layout to flexDirection
      // row) rather than a tall bar still stacked above/below the content.
      tabBar={Platform.OS === 'web' ? (props) => <WebSidebarNav {...props} /> : undefined}
      screenOptions={{
        tabBarPosition: Platform.OS === 'web' ? 'left' : 'bottom',
        headerStyle: { backgroundColor: colors.surface },
        headerTitleStyle: { fontFamily: fontFamily.semiBold, fontSize: 20, color: colors.textPrimary },
        headerTintColor: colors.primary,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
        // On web the WebSidebarNav component owns its own width/padding —
        // this only needs to stay out of its way, not size it (a fixed
        // `height: 68`, correct for a bottom bar, would be wrong for a left
        // sidebar's cross-axis).
        tabBarStyle: Platform.OS === 'web' ? { backgroundColor: colors.surface } : {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          height: 68,
          paddingTop: 8,
          paddingBottom: 10,
        },
        tabBarLabelStyle: { fontFamily: fontFamily.semiBold, fontSize: 12 },
      }}
    >
      <Tab.Screen
        name="HomeTab"
        component={HomeDashboardScreen}
        options={{
          headerShown: false,
          tabBarLabel: t('tabs.home'),
          tabBarIcon: ({ color, size, focused }) => (
            <Ionicons name={focused ? 'home' : 'home-outline'} color={color} size={size} />
          ),
        }}
      />
      <Tab.Screen
        name="KundaliTab"
        component={CompleteKundaliScreen}
        options={{
          title: t('kundali.screenTitle'),
          tabBarLabel: t('tabs.kundali'),
          tabBarIcon: ({ color, size, focused }) => (
            <Ionicons name={focused ? 'book' : 'book-outline'} color={color} size={size} />
          ),
        }}
      />
      <Tab.Screen
        name="VoiceTab"
        component={RishiStack}
        options={{
          headerShown: false,
          tabBarLabel: () => null,
          tabBarIcon: ({ color }) => <Ionicons name="chatbubbles" size={30} color={colors.textOnPrimary ?? color} />,
          tabBarButton: (props) => <CenterMicButton {...props} />,
        }}
      />
      <Tab.Screen
        name="ChartsTab"
        component={ChartsScreen}
        options={{
          title: t('charts.screenTitle'),
          tabBarLabel: t('tabs.charts'),
          tabBarIcon: ({ color, size, focused }) => (
            <Ionicons name={focused ? 'pie-chart' : 'pie-chart-outline'} color={color} size={size} />
          ),
        }}
      />
      <Tab.Screen
        name="ProfileTab"
        component={ProfileScreen}
        options={{
          title: t('profile.screenTitle'),
          tabBarLabel: t('tabs.profile'),
          tabBarIcon: ({ color, size, focused }) => (
            <Ionicons name={focused ? 'person-circle' : 'person-circle-outline'} color={color} size={size} />
          ),
        }}
      />
    </Tab.Navigator>
  );
}

const styles = StyleSheet.create({
  centerButtonWrap: {
    top: -22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  centerButton: {
    width: 68,
    height: 68,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 4,
    borderColor: colors.surface,
    shadowColor: elevation.raised.shadowColor,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: elevation.raised.shadowOpacity,
    shadowRadius: elevation.raised.shadowRadius,
    elevation: elevation.raised.elevation,
  },
  centerButtonActive: {
    backgroundColor: colors.primaryDark,
  },
});
