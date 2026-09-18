import { ChartType, Language, OuterPlanetKey, PlanetKey } from '../types/kundali';

// Fixed zodiac order, index 0 = Aries ... 11 = Pisces.
export const SIGN_NAMES: Record<Language, string[]> = {
  en: [
    'Aries',
    'Taurus',
    'Gemini',
    'Cancer',
    'Leo',
    'Virgo',
    'Libra',
    'Scorpio',
    'Sagittarius',
    'Capricorn',
    'Aquarius',
    'Pisces',
  ],
  hi: [
    'मेष',
    'वृषभ',
    'मिथुन',
    'कर्क',
    'सिंह',
    'कन्या',
    'तुला',
    'वृश्चिक',
    'धनु',
    'मकर',
    'कुंभ',
    'मीन',
  ],
};

// Unicode zodiac glyphs, same index order as SIGN_NAMES (0 = Aries).
export const SIGN_GLYPHS = ['♈', '♉', '♊', '♋', '♌', '♍', '♎', '♏', '♐', '♑', '♒', '♓'];

export const PLANET_ORDER: PlanetKey[] = ['Su', 'Mo', 'Ma', 'Me', 'Ju', 'Ve', 'Sa', 'Ra', 'Ke'];

// Classical astrological glyphs, one per graha.
export const PLANET_GLYPHS: Record<PlanetKey, string> = {
  Su: '☉', Mo: '☽', Ma: '♂', Me: '☿', Ju: '♃', Ve: '♀', Sa: '♄', Ra: '☊', Ke: '☋',
};

// A signature tint per graha for the chart display — kept warm/muted (no
// alarm-red, matching the rest of the app's palette philosophy).
export const PLANET_COLORS: Record<PlanetKey, string> = {
  Su: '#C9750A', Mo: '#5B7C99', Ma: '#7A3B2E', Me: '#3E7A4C', Ju: '#8A5A00',
  Ve: '#A9578F', Sa: '#4A4038', Ra: '#5C2C22', Ke: '#8C6239',
};

export const PLANET_NAMES: Record<Language, Record<PlanetKey, string>> = {
  en: {
    Su: 'Sun',
    Mo: 'Moon',
    Ma: 'Mars',
    Me: 'Mercury',
    Ju: 'Jupiter',
    Ve: 'Venus',
    Sa: 'Saturn',
    Ra: 'Rahu',
    Ke: 'Ketu',
  },
  hi: {
    Su: 'सूर्य',
    Mo: 'चंद्र',
    Ma: 'मंगल',
    Me: 'बुध',
    Ju: 'गुरु',
    Ve: 'शुक्र',
    Sa: 'शनि',
    Ra: 'राहु',
    Ke: 'केतु',
  },
};

// Uranus/Neptune/Pluto — display-only chart placements, kept in their own
// tables rather than folded into PLANET_GLYPHS/COLORS/NAMES above (see
// OuterPlanetKey's docstring for why they're a separate type entirely).
export const OUTER_PLANET_GLYPHS: Record<OuterPlanetKey, string> = {
  Ur: '⛢', Ne: '♆', Pl: '♇',
};

export const OUTER_PLANET_COLORS: Record<OuterPlanetKey, string> = {
  Ur: '#6B8E9E', Ne: '#5B6BA8', Pl: '#8B5E6B',
};

export const OUTER_PLANET_NAMES: Record<Language, Record<OuterPlanetKey, string>> = {
  en: { Ur: 'Uranus', Ne: 'Neptune', Pl: 'Pluto' },
  hi: { Ur: 'यूरेनस', Ne: 'नेपच्यून', Pl: 'प्लूटो' },
};

export const CHART_LABELS: Record<Language, Record<ChartType, string>> = {
  en: { D1: 'D1 — Rasi (Birth Chart)', D9: 'D9 — Navamsa (Marriage & Fortune)', D10: 'D10 — Dashamsa (Career)' },
  hi: { D1: 'D1 — राशि चक्र (जन्म कुंडली)', D9: 'D9 — नवमांश (विवाह व भाग्य)', D10: 'D10 — दशमांश (करियर)' },
};

// South Indian chart layout: signs sit in fixed grid cells (a permanent ring),
// starting at Pisces top-left and continuing clockwise through natural zodiac
// order. House numbers are relative to the Lagna sign and computed at render
// time, so only the sign placement needs to be fixed here.
export const RING_SIGN_INDEX = [11, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]; // Pisces..Aquarius, ring position 0..11

export const RING_CELL: [number, number][] = [
  [0, 0],
  [0, 1],
  [0, 2],
  [0, 3],
  [1, 3],
  [2, 3],
  [3, 3],
  [3, 2],
  [3, 1],
  [3, 0],
  [2, 0],
  [1, 0],
];

export function houseNumberForSign(signIndex: number, lagnaSignIndex: number): number {
  return ((signIndex - lagnaSignIndex + 12) % 12) + 1;
}
