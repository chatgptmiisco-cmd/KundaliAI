import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, elevation, minTouchTarget, radius, spacing, typography } from '../theme/theme';

interface Props {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'outline';
  icon?: React.ReactNode;
  loading?: boolean;
  disabled?: boolean;
  accessibilityHint?: string;
}

export default function PrimaryButton({
  label,
  onPress,
  variant = 'primary',
  icon,
  loading,
  disabled,
  accessibilityHint,
}: Props) {
  const isDisabled = disabled || loading;
  // `primary`'s background is the light gold accent (needs dark ink text);
  // `secondary` (rose) and the disabled state are medium/dark and need the
  // usual light `textInverse`; `outline` has no fill, so its own color reads.
  const foregroundColor =
    variant === 'outline' ? colors.primary : variant === 'primary' && !isDisabled ? colors.textOnPrimary : colors.textInverse;
  return (
    <Pressable
      onPress={onPress}
      disabled={isDisabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: isDisabled }}
      style={({ pressed }) => [
        styles.base,
        variant === 'primary' && styles.primary,
        variant === 'secondary' && styles.secondary,
        variant === 'outline' && styles.outline,
        isDisabled && styles.disabled,
        pressed && !isDisabled && styles.pressed,
      ]}
    >
      <View style={styles.content}>
        {loading ? (
          <ActivityIndicator color={foregroundColor} />
        ) : (
          <>
            {icon}
            <Text style={[styles.label, { color: foregroundColor }]} numberOfLines={2}>
              {label}
            </Text>
          </>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: minTouchTarget,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    justifyContent: 'center',
    alignItems: 'center',
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  primary: {
    backgroundColor: colors.primary,
    ...elevation.card,
  },
  secondary: {
    backgroundColor: colors.accent,
    ...elevation.card,
  },
  outline: {
    backgroundColor: colors.surface,
    borderWidth: 2,
    borderColor: colors.primary,
  },
  disabled: {
    backgroundColor: colors.disabled,
  },
  pressed: {
    opacity: 0.85,
  },
  label: {
    ...typography.button,
    color: colors.textInverse,
    textAlign: 'center',
  },
});
