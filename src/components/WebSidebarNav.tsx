import { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fontFamily, radius, spacing } from '../theme/theme';

const SIDEBAR_WIDTH = 220;
const ICON_SIZE = 22;

// The web-only chrome swapped in for the bottom tab bar (see MainTabs.tsx's
// `Platform.OS === 'web'` branch on the `tabBar` prop) — reads every
// destination straight off the SAME route/descriptor data the native bottom
// bar already uses (tabBarIcon/tabBarLabel/title from each Tab.Screen's own
// `options`), so there's exactly one place (MainTabs.tsx) that defines what
// the 5 destinations are; this is purely a different way of laying the same
// data out, never a second source of truth for it.
export default function WebSidebarNav({ state, descriptors, navigation }: BottomTabBarProps) {
  return (
    <View style={styles.sidebar}>
      <Text style={styles.brand}>KundaliAI</Text>
      <View style={styles.items}>
        {state.routes.map((route, index) => {
          const { options } = descriptors[route.key];
          const focused = state.index === index;
          const color = focused ? colors.primary : colors.textSecondary;
          const label =
            typeof options.tabBarLabel === 'string'
              ? options.tabBarLabel
              : (options.title ?? route.name);
          // The center "Ask a Rishi" tab hides its label on the phone bar
          // (tabBarLabel: () => null, a big circular button instead) — the
          // sidebar has no room-constrained icon-only row to justify that
          // here, so it always gets a real text label like every other item.
          const displayLabel = typeof label === 'string' && label ? label : 'Chat';

          const onPress = () => {
            const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
            if (!focused && !event.defaultPrevented) {
              navigation.navigate(route.name);
            }
          };

          return (
            <Pressable
              key={route.key}
              onPress={onPress}
              accessibilityRole="button"
              accessibilityState={focused ? { selected: true } : {}}
              style={({ pressed }) => [styles.item, focused && styles.itemActive, pressed && styles.itemPressed]}
            >
              {options.tabBarIcon?.({ color, size: ICON_SIZE, focused })}
              <Text style={[styles.itemLabel, { color }]}>{displayLabel}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  sidebar: {
    width: SIDEBAR_WIDTH,
    backgroundColor: colors.surface,
    borderRightWidth: 1,
    borderRightColor: colors.border,
    paddingVertical: spacing.xl,
    paddingHorizontal: spacing.md,
    gap: spacing.lg,
  },
  brand: {
    fontFamily: fontFamily.displayBold,
    fontSize: 22,
    color: colors.primary,
    paddingHorizontal: spacing.sm,
  },
  items: {
    gap: spacing.xs,
  },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.md,
  },
  itemActive: {
    backgroundColor: colors.accentLight,
  },
  itemPressed: {
    opacity: 0.85,
  },
  itemLabel: {
    fontFamily: fontFamily.semiBold,
    fontSize: 15,
  },
});
