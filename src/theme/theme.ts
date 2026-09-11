// Calm, senior-friendly theme. No alarm-red anywhere in the palette —
// Manglik / attention states use amber-orange instead of red.
export const colors = {
  background: '#FBF7F1',
  surface: '#FFFFFF',
  surfaceMuted: '#F3ECE0',

  textPrimary: '#2B241C',
  textSecondary: '#5B5044',
  textInverse: '#FFFFFF',

  primary: '#7A3B2E', // deep maroon — auspicious, warm, not aggressive
  primaryDark: '#5C2C22',
  primaryLight: '#F1DED7',

  accent: '#C9750A', // amber-orange for attention (never red)
  accentLight: '#FCEACB',
  accentDark: '#8C5107',

  success: '#3E7A4C',
  successLight: '#E4F2E6',

  border: '#E4D9C8',

  premium: '#8A5A00',
  premiumLight: '#FBEBCE',

  disabled: '#C9C2B6',

  shadow: '#3A2A1E',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 40,
};

export const radius = {
  sm: 8,
  md: 14,
  lg: 20,
  xl: 28,
  pill: 999,
};

// Card/button elevation — a soft, warm-toned shadow rather than flat borders,
// which is what reads as a wireframe/prototype instead of a finished app.
export const elevation = {
  card: {
    shadowColor: colors.shadow,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.08,
    shadowRadius: 10,
    elevation: 3,
  },
  raised: {
    shadowColor: colors.shadow,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.14,
    shadowRadius: 16,
    elevation: 6,
  },
};

// Two bilingual type families (both Latin + Devanagari, so headings render
// correctly in Hindi too — a Latin-only display font would silently drop
// Hindi glyphs). Baloo 2 is a rounded, distinctive display face used for the
// biggest headings; Mukta is a smoother, warmer workhorse for everything
// read at length — same Indian Type Foundry lineage as Baloo 2, so the two
// pair cleanly instead of looking like two unrelated typefaces bolted
// together.
export const fontFamily = {
  regular: 'Mukta_400Regular',
  medium: 'Mukta_500Medium',
  semiBold: 'Mukta_600SemiBold',
  bold: 'Mukta_700Bold',
  displayBold: 'Baloo2_700Bold',
  displayExtraBold: 'Baloo2_800ExtraBold',
};

// Senior-friendly type scale: generous sizes, high line-height for readability.
export const typography = {
  display: { fontSize: 30, lineHeight: 40, fontFamily: fontFamily.displayExtraBold },
  statusLine: { fontSize: 26, lineHeight: 36, fontFamily: fontFamily.displayBold },
  title: { fontSize: 22, lineHeight: 30, fontFamily: fontFamily.displayBold },
  sectionTitle: { fontSize: 20, lineHeight: 28, fontFamily: fontFamily.semiBold },
  body: { fontSize: 18, lineHeight: 27, fontFamily: fontFamily.regular },
  bodyBold: { fontSize: 18, lineHeight: 27, fontFamily: fontFamily.semiBold },
  button: { fontSize: 18, lineHeight: 24, fontFamily: fontFamily.semiBold },
  caption: { fontSize: 15, lineHeight: 21, fontFamily: fontFamily.medium },
};

export const minTouchTarget = 48;

export const theme = { colors, spacing, radius, elevation, fontFamily, typography, minTouchTarget };
export type Theme = typeof theme;
