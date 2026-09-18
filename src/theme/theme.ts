// "Astrolabe Glass" — a night-sky, glassmorphism theme (approved design
// direction, see the "Astrolabe Glass" mockup). Every token below keeps its
// ORIGINAL NAME from the old warm-cream theme, just repointed to dark-theme
// values — every screen already reads color through these names (not
// hardcoded hex), so this one file is what actually reskins the whole app.
// Still no alarm-red anywhere — Manglik/attention states stay amber-gold.
export const colors = {
  background: '#120B22', // deep indigo night sky, not flat black
  surface: '#1C1233', // panels that aren't glass (rare — most surfaces are glass now, see `glass` below)
  surfaceMuted: '#241A3D',

  textPrimary: '#F4EEE2', // warm off-white, not clinical pure white
  textSecondary: '#C9BEDD', // soft lavender-grey
  // Light text for content sitting on a medium/dark colored surface (a
  // per-Rishi gradient portrait, the rose accent, an icon on a dark header)
  // — kept white/light exactly like the old theme, since every one of
  // those surfaces is still medium-to-dark. The ONE new exception is text
  // sitting directly on the gold `primary` color itself, which is light —
  // see `textOnPrimary` below, used only there.
  textInverse: '#FFFFFF',
  // Dark ink — for text/icons placed directly on the gold `primary` color
  // (buttons, active tab pills, chips), which is light and would swallow
  // white text. Nowhere else: every other colored surface in this app is
  // still medium-to-dark and wants `textInverse` instead.
  textOnPrimary: '#241608',

  primary: '#D8A85C', // brass/gold — the astrolabe accent, replaces maroon as the lead color
  primaryDark: '#9C7C48',
  primaryLight: '#F0D9A8',

  accent: '#C97361', // warm rose (the old maroon primary, lightened for dark bg) — secondary accent, user-message bubbles
  // Transparent rose tint (not a solid color) — same "sits over whatever
  // background is behind it" pattern as successLight/premiumLight below.
  // An earlier solid dark-plum value here paired badly with accentDark
  // text (dark-on-dark, same family of bug as the primaryLight fixes).
  accentLight: 'rgba(201,115,97,0.16)',
  accentDark: '#8C4A3E',

  success: '#7FAE8A',
  successLight: 'rgba(127,174,138,0.14)',

  border: 'rgba(244,238,226,0.14)',

  premium: '#D8A85C',
  premiumLight: 'rgba(216,168,92,0.16)',

  disabled: '#584C74',

  shadow: '#05030B',
};

// Frosted-glass surface tokens — every card/sheet/composer bar in the new
// design is real glass (see components/GlassSurface.tsx), not a flat
// colored rectangle. `fill`/`fillStrong` are meant to sit OVER a BlurView,
// which is what actually produces the blur; these alone are just a tinted
// see-through layer (Android's fallback when real blur isn't wired up for
// a given spot — see GlassSurface's doc comment).
export const glass = {
  fill: 'rgba(244,238,226,0.06)',
  fillStrong: 'rgba(244,238,226,0.10)',
  border: 'rgba(216,168,92,0.32)',
  borderSoft: 'rgba(244,238,226,0.14)',
  blurIntensity: 40,
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

export const theme = { colors, glass, spacing, radius, elevation, fontFamily, typography, minTouchTarget };
export type Theme = typeof theme;
