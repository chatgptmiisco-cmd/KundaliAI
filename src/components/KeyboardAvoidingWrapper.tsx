import React from 'react';
import { KeyboardAvoidingView, Platform, StyleProp, StyleSheet, ViewStyle } from 'react-native';

interface Props {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}

/** Wraps any screen holding a TextInput so the keyboard slides the field/
 * button actually being used up out from under itself instead of covering
 * it — drop this in place of (or just inside) whatever a screen's own
 * outermost flex:1 container already is.
 *
 * Both platforms get an explicit behavior now — caught live, reproduced:
 * Android was left with `behavior={undefined}` on the assumption that
 * Expo's default `windowSoftInputMode` (`adjustResize`) would handle it at
 * the native/window level, but that wasn't actually active in the running
 * build, so the composer/input was left completely hidden behind the
 * keyboard with NOTHING compensating for it. `"height"` shrinks this
 * view's own height on the keyboard's show/hide events regardless of
 * whatever the native window mode is doing — if adjustResize ever IS
 * active too, the worst case is some extra empty space above the
 * keyboard, which is a far smaller problem than the field being hidden
 * entirely. */
export default function KeyboardAvoidingWrapper({ children, style }: Props) {
  return (
    <KeyboardAvoidingView style={[styles.flex, style]} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      {children}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
});
