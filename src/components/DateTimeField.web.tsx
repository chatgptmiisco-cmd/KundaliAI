import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { colors, radius, spacing, typography } from '../theme/theme';

interface Props {
  label: string;
  mode: 'date' | 'time';
  value: string; // 'YYYY-MM-DD' for date mode, 'HH:mm' for time mode
  onChange: (value: string) => void;
  placeholder: string;
  maximumDate?: Date;
  minimumDate?: Date;
}

function toDateInputValue(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Web build of DateTimeField (Metro picks this over DateTimeField.tsx when
 * bundling for web — same platform-extension convention the datetimepicker
 * library itself uses) — @react-native-community/datetimepicker ships
 * .android.js/.ios.js/.windows.js variants but NO .web.js at all, so the
 * native version silently did nothing on web, making the date/time boxes
 * look non-editable. The browser's own <input type="date">/type="time">
 * is a real, fully-functional picker here, and its value format ('YYYY-
 * MM-DD' / 'HH:mm') already matches what this app stores — no parsing
 * needed either way. */
export default function DateTimeField({ label, mode, value, onChange, placeholder, maximumDate, minimumDate }: Props) {
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      {React.createElement('input', {
        type: mode,
        value: value || '',
        placeholder,
        max: mode === 'date' && maximumDate ? toDateInputValue(maximumDate) : undefined,
        min: mode === 'date' && minimumDate ? toDateInputValue(minimumDate) : undefined,
        onChange: (e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value),
        style: {
          fontFamily: 'inherit',
          fontSize: 18,
          color: colors.textPrimary,
          border: `1.5px solid ${colors.border}`,
          borderRadius: radius.md,
          paddingLeft: spacing.md,
          paddingRight: spacing.md,
          minHeight: 48,
          backgroundColor: colors.background,
          width: '100%',
          boxSizing: 'border-box' as const,
        },
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  label: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
});
