import { Ionicons } from '@expo/vector-icons';
import DateTimePicker, { DateTimePickerAndroid, DateTimePickerEvent } from '@react-native-community/datetimepicker';
import React, { useState } from 'react';
import { Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { colors, elevation, radius, spacing, typography } from '../theme/theme';

interface Props {
  label: string;
  mode: 'date' | 'time';
  value: string; // 'YYYY-MM-DD' for date mode, 'HH:mm' for time mode
  onChange: (value: string) => void;
  placeholder: string;
  maximumDate?: Date;
  minimumDate?: Date;
}

function parseValue(mode: 'date' | 'time', value: string): Date {
  const now = new Date();
  if (mode === 'date') {
    const [y, m, d] = value.split('-').map(Number);
    if (!y || !m || !d) return now;
    return new Date(y, m - 1, d);
  }
  const [h, min] = value.split(':').map(Number);
  if (Number.isNaN(h) || Number.isNaN(min)) return now;
  const dt = new Date();
  dt.setHours(h, min, 0, 0);
  return dt;
}

function formatValue(mode: 'date' | 'time', date: Date): string {
  if (mode === 'date') {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }
  const h = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');
  return `${h}:${min}`;
}

/** Native date/time picker in place of free-text entry — a typed birth
 * date/time had zero format or range validation before this (a plain
 * TextInput would happily accept "banana" as a date of birth). Android
 * opens the OS dialog imperatively (the standard pattern for this library);
 * iOS renders an inline spinner in a small sheet with an explicit confirm,
 * since iOS's spinner mode doesn't auto-dismiss on selection. */
export default function DateTimeField({ label, mode, value, onChange, placeholder, maximumDate, minimumDate }: Props) {
  const { t } = useTranslation();
  const [iosPickerVisible, setIosPickerVisible] = useState(false);
  const [draftDate, setDraftDate] = useState<Date>(() => parseValue(mode, value || ''));

  const openPicker = () => {
    const current = parseValue(mode, value || '');
    if (Platform.OS === 'android') {
      DateTimePickerAndroid.open({
        value: current,
        mode,
        maximumDate,
        minimumDate,
        onChange: (event: DateTimePickerEvent, selected?: Date) => {
          if (event.type === 'set' && selected) {
            onChange(formatValue(mode, selected));
          }
        },
      });
    } else {
      setDraftDate(current);
      setIosPickerVisible(true);
    }
  };

  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <Pressable onPress={openPicker} style={styles.input} accessibilityRole="button" accessibilityLabel={label}>
        <Text style={value ? styles.valueText : styles.placeholderText}>{value || placeholder}</Text>
        <Ionicons name={mode === 'date' ? 'calendar-outline' : 'time-outline'} size={20} color={colors.textSecondary} />
      </Pressable>

      {Platform.OS === 'ios' && (
        <Modal
          transparent
          visible={iosPickerVisible}
          animationType="fade"
          onRequestClose={() => setIosPickerVisible(false)}
        >
          <Pressable style={styles.backdrop} onPress={() => setIosPickerVisible(false)}>
            <Pressable style={styles.sheet} onPress={() => {}}>
              <DateTimePicker
                value={draftDate}
                mode={mode}
                display="spinner"
                maximumDate={maximumDate}
                minimumDate={minimumDate}
                onChange={(_, selected) => selected && setDraftDate(selected)}
              />
              <Pressable
                style={styles.doneButton}
                onPress={() => {
                  onChange(formatValue(mode, draftDate));
                  setIosPickerVisible(false);
                }}
              >
                <Text style={styles.doneButtonText}>{t('common.save')}</Text>
              </Pressable>
            </Pressable>
          </Pressable>
        </Modal>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  label: {
    ...typography.caption,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  input: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    minHeight: 48,
    backgroundColor: colors.background,
  },
  valueText: {
    ...typography.body,
    color: colors.textPrimary,
  },
  placeholderText: {
    ...typography.body,
    color: colors.textSecondary,
  },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(43,36,28,0.45)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.lg,
  },
  sheet: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.lg,
    width: '100%',
    maxWidth: 400,
    ...elevation.raised,
  },
  doneButton: {
    marginTop: spacing.md,
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    alignItems: 'center',
  },
  doneButtonText: {
    ...typography.button,
    color: colors.textInverse,
  },
});
