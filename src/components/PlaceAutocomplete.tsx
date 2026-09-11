import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { GeocodeResult, searchPlaces } from '../data/geocoding';
import { colors, elevation, radius, spacing, typography } from '../theme/theme';

interface Props {
  value: string;
  placeholder?: string;
  onSelect: (result: GeocodeResult) => void;
  // Fired on every keystroke, including ones that don't (yet) resolve to a
  // selected suggestion — the caller uses this to clear any previously
  // selected lat/long so a stale coordinate never ships alongside edited
  // text that no longer matches it.
  onChangeText: (text: string) => void;
}

const DEBOUNCE_MS = 400;

/** Search-as-you-type birth-place lookup (OpenStreetMap Nominatim, see
 * data/geocoding.ts) — replaces free-text-only entry, where a typo or an
 * unlisted town used to silently resolve to New Delhi's coordinates with no
 * indication anything was wrong. */
export default function PlaceAutocomplete({ value, placeholder, onSelect, onChangeText }: Props) {
  const { t } = useTranslation();
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [failed, setFailed] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const runSearch = (text: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (text.trim().length < 3) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setFailed(false);
    const requestId = ++requestIdRef.current;
    debounceRef.current = setTimeout(async () => {
      try {
        const found = await searchPlaces(text);
        // Ignore a stale response that resolved after a newer keystroke
        // already started a different search.
        if (requestId !== requestIdRef.current) return;
        setResults(found);
      } catch {
        if (requestId !== requestIdRef.current) return;
        setResults([]);
        setFailed(true);
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    }, DEBOUNCE_MS);
  };

  const handleChangeText = (text: string) => {
    onChangeText(text);
    setShowResults(true);
    runSearch(text);
  };

  const handleSelect = (result: GeocodeResult) => {
    setShowResults(false);
    setResults([]);
    onSelect(result);
  };

  return (
    <View>
      <View style={styles.inputRow}>
        <TextInput
          value={value}
          onChangeText={handleChangeText}
          onFocus={() => setShowResults(true)}
          placeholder={placeholder}
          placeholderTextColor={colors.textSecondary}
          style={styles.input}
        />
        {loading && <ActivityIndicator size="small" color={colors.primary} style={styles.spinner} />}
      </View>

      {showResults && (results.length > 0 || failed) && (
        <View style={styles.dropdown}>
          {results.map((r) => (
            <Pressable
              key={`${r.latitude},${r.longitude}`}
              onPress={() => handleSelect(r)}
              style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
            >
              <Text style={styles.rowText} numberOfLines={2}>
                {r.displayName}
              </Text>
            </Pressable>
          ))}
          {failed && <Text style={styles.errorText}>{t('profile.placeSearchError')}</Text>}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  inputRow: {
    justifyContent: 'center',
  },
  input: {
    ...typography.body,
    color: colors.textPrimary,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingRight: spacing.xl,
    minHeight: 48,
    backgroundColor: colors.background,
  },
  spinner: {
    position: 'absolute',
    right: spacing.md,
  },
  dropdown: {
    marginTop: spacing.xs,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    ...elevation.card,
    overflow: 'hidden',
  },
  row: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  rowPressed: {
    backgroundColor: colors.surfaceMuted,
  },
  rowText: {
    ...typography.caption,
    color: colors.textPrimary,
  },
  errorText: {
    ...typography.caption,
    color: colors.accentDark,
    padding: spacing.sm,
  },
});
