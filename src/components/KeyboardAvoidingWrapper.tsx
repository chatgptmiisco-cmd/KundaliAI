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
 * iOS has no automatic layout resize when the keyboard opens, so only iOS
 * gets the "padding" behavior; Android already resizes the window itself
 * (Expo's default softwareKeyboardLayoutMode), so adding a second resize
 * on top would double-compensate and cause an extra jump — left alone
 * there (`behavior={undefined}`) on purpose, not an oversight. */
export default function KeyboardAvoidingWrapper({ children, style }: Props) {
  return (
    <KeyboardAvoidingView style={[styles.flex, style]} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {children}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
});
