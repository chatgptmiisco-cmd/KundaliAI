export type Language = 'en' | 'hi';

// UI chrome can also run in Hinglish; astrological content itself is only
// ever generated in English or Hindi (see toContentLanguage()).
export type AppLanguage = 'en' | 'hi' | 'hinglish';

export type PlanTier = 'free' | 'insight' | 'strategy';

export interface BirthData {
  name: string;
  dateOfBirth: string; // ISO date
  timeOfBirth: string; // HH:mm
  placeOfBirth: string;
  // Populated when the user picks a real geocoded suggestion for
  // placeOfBirth (see components/PlaceAutocomplete + data/geocoding) —
  // preferred over the offline city-table fallback (resolveBirthPlace)
  // whenever present. Cleared if the user edits the place text afterward,
  // since a stale coordinate no longer matching the typed text is worse
  // than falling back to the table.
  latitude?: number;
  longitude?: number;
  timezoneOffsetHours?: number;
}

export interface KundaliSummary {
  lagna: string;
  moonSign: string;
  coreStrength: string;
  coreChallenge: string;
  manglik: {
    isManglik: boolean;
    oneLiner: string;
  };
}

export interface ManglikStatus {
  isManglik: boolean;
  summary: string;
  marsHouseFromLagna: number;
  marsHouseFromMoon: number;
  details: string[];
  cancellations: string[];
  relationshipNote: string;
}

export interface KootaScore {
  key: string;
  label: string;
  score: number;
  maxScore: number;
  summary: string;
}

export interface ValidationQuestion {
  periodStart: string;
  periodEnd: string;
  lord: PlanetKey;
  house: number;
  statement: string;
}

export interface GunaMilanResult {
  yourMoonSign: string;
  yourNakshatra: string;
  partnerMoonSign: string;
  partnerNakshatra: string;
  totalScore: number;
  maxTotal: number;
  kootas: KootaScore[];
  mangalDoshaMismatch: boolean;
  mangalDoshaNote: string | null;
  verdict: 'excellent' | 'good' | 'average' | 'not_recommended';
  verdictMessage: string;
}

export interface KeyValueItem {
  label: string;
  value: string;
}

export interface KundaliSection {
  id:
    | 'personalityNature'
    | 'careerMoney'
    | 'relationshipsMarriage'
    | 'healthTemperament'
    | 'strengthsChallenges'
    | 'timingOverview';
  title: string;
  summary: string;
  keyPoints: string[];
}

export interface KundaliComplete {
  generatedAt: string;
  language: Language;
  basicDetails: KeyValueItem[];
  sections: KundaliSection[];
  manglik: ManglikStatus;
  brutalTruth: string;
}

export interface VoiceClip {
  sectionId: string;
  language: Language;
  audioAvailable: boolean;
}

export type ChartType = 'D1' | 'D9' | 'D10';

export type PlanetKey = 'Su' | 'Mo' | 'Ma' | 'Me' | 'Ju' | 'Ve' | 'Sa' | 'Ra' | 'Ke';

/** Uranus/Neptune/Pluto — deliberately kept OUT of PlanetKey. They're not
 * part of classical Jyotish (no dasha period, no house lordship, no
 * dignity/friendship/aspect rules), so every `Record<PlanetKey, ...>` in
 * this app (dasha, lordship, glyphs/colors/names) can stay exhaustive
 * without meaningless entries for them. Shown on the chart purely for
 * visual parity with common reference charts. */
export type OuterPlanetKey = 'Ur' | 'Ne' | 'Pl';

export type Dignity = 'exalted' | 'debilitated' | 'own_sign' | 'neutral';

/** "Grah Spashta" precision detail for one planet — real computed values,
 * not narrative text: exact degree within sign (D1 only), nakshatra + pada,
 * and classical dignity. */
export interface PlanetDetail {
  planet: PlanetKey;
  signIndex: number;
  house: number;
  retrograde: boolean;
  degreeInSign: number | null;
  degreeDisplay: string | null;
  nakshatraName: string | null;
  nakshatraPada: number | null;
  dignity: Dignity | null;
  combust: boolean | null;
}

/** What's in one house and what that combination means in plain language —
 * the "what thing is affecting what" explanation the Charts tab was missing. */
export interface HouseBreakdown {
  house: number;
  signNameEn: string;
  signNameHi: string;
  planets: PlanetKey[];
  explanationEn: string;
  explanationHi: string;
}

/** A detected classical yoga or dosha (Gajakesari, Panch Mahapurusha, a
 * conservative Raj Yoga, Manglik, Kaal Sarp, Kemadruma) — D1 only. */
export interface YogaFinding {
  key: string;
  nameEn: string;
  nameHi: string;
  descriptionEn: string;
  descriptionHi: string;
}

/** A Uranus/Neptune/Pluto placement — the same shape a PlanetDetail would
 * need for chart drawing (sign/house/retrograde), minus the classical-only
 * fields (dignity, combustion, nakshatra) that don't apply to them. */
export interface OuterPlanetPlacement {
  planet: OuterPlanetKey;
  signIndex: number;
  house: number;
  retrograde: boolean;
  degreeDisplay: string | null;
}

export interface BirthChart {
  type: ChartType;
  lagnaSignIndex: number; // 0 = Aries ... 11 = Pisces
  lagnaDegreeDisplay: string | null;
  planetSignIndex: Record<PlanetKey, number>;
  planetRetrograde: Partial<Record<PlanetKey, boolean>>;
  planetDetails: Partial<Record<PlanetKey, PlanetDetail>>;
  summary: string;
  keyPoints: string[];
  houseBreakdown: HouseBreakdown[];
  yogas: YogaFinding[];
  // Display-only — never used for dasha/lordship/dosha logic, see
  // OuterPlanetKey's docstring above.
  outerPlanets: OuterPlanetPlacement[];
}

export interface DashaSubPeriod {
  planet: PlanetKey;
  startDate: string;
  endDate: string;
  isCurrent: boolean;
}

export interface DashaPeriod {
  planet: PlanetKey;
  startDate: string;
  endDate: string;
  isCurrent: boolean;
  subPeriods: DashaSubPeriod[];
}

/** The three-level dasha stack active right now (Mahadasha > Antardasha >
 * Pratyantardasha) — the Pratyantardasha is the most precise "which weeks/
 * months exactly" window the engine computes, and previously never reached
 * the UI at all. */
export interface CurrentDashaLevel {
  planet: PlanetKey;
  startDate: string;
  endDate: string;
}

export interface CurrentDasha {
  mahadasha: CurrentDashaLevel;
  antardasha: CurrentDashaLevel;
  pratyantardasha: CurrentDashaLevel;
}

/** Real, backend-calculated reading for one date range (used for both the
 * "current period" analysis and any historical Dasha period on demand). */
export interface PeriodAnalysis {
  rating: number; // 1-10
  theme: string;
  risks: string[];
  opportunities: string[];
  remainingFreeAnalysesThisMonth: number | null;
  summary: string;
}

export interface DoshaSummaryItem {
  key: string;
  label: string;
  isPresent: boolean;
}

/** The full "today" reading — every field traced to a real calculation off
 * the natal chart, running dasha, and today's transits/panchang. */
export interface DailyReading {
  date: string;
  rating: number;
  ratingReason: string;
  dominantTheme: string;
  energyMode: string;
  keyRisk: string;
  keyOpportunity: string;
  brutalTruth: string;
  mahadashaLabel: string;
  periodRating: number;
  periodType: string;
  dominantLifeArea: string;
  coreStrength: string;
  coreWeakness: string;
  stressPattern: string;
  decisionStyle: string;
  moonNakshatra: string;
  moonMoodTag: string;
  transitHighlight: string;
  beforeYouLeaveHome: string[];
  lifeGrowthTask: string;
  tithiTag: string;
  tithiName: string;
  paksha: string;
  lunarMonth: string;
  festival: string | null;
  todayColor: string;
  luckyNumber: number;
  todayGuidance: string[];
  doshas: DoshaSummaryItem[];
  jupiterTransitingMoonSign: boolean;
}

/** How today looks for one specific focus area (family/health/career/
 * marriage & relationships/friends) — the house that classically governs it,
 * who rules that house, how well-placed they are, and any transit sharpening
 * it today. Powers the swipeable focus tabs on Home. */
export interface FocusAreaReading {
  area: string;
  house: number;
  houseLord: PlanetKey;
  houseLordHouse: number;
  dignity: Dignity;
  rating: number;
  theme: string;
  summary: string;
  meaning: string;
  avoidToday: string;
  focusToday: string;
  transitNote: string | null;
}

/** Layer 1 of the Charts redesign — the "Identity Basics" hook: Big Three
 * (Lagna/Moon-sign/Sun-sign) with a fixed one-line meaning each, the birth
 * (Moon) nakshatra with its lord/symbol/meaning, and an element+modality
 * breakdown across Lagna + the 9 grahas. Both languages come in one payload
 * (same convention as BirthChart's houseBreakdown), so this is fetched once. */
export interface SignIdentity {
  signEn: string;
  signHi: string;
  // What this point classically represents — fixed reference copy, the same
  // for anyone with this Lagna/Moon/Sun.
  meaningEn: string;
  meaningHi: string;
  // The real, per-chart consequence: where this point sits and how well
  // placed it is, and what that means for this specific user. Lead with
  // this; `meaning*` is the secondary glossary note.
  realEffectEn: string;
  realEffectHi: string;
}

export interface NakshatraIdentity {
  nameEn: string;
  nameHi: string;
  pada: number;
  lordEn: string;
  lordHi: string;
  symbolEn: string;
  symbolHi: string;
  meaningEn: string;
  meaningHi: string;
}

export interface ElementModalityPoint {
  pointKey: string; // "Lagna" | PlanetKey
  pointLabelEn: string;
  pointLabelHi: string;
  elementEn: string;
  elementHi: string;
  modalityEn: string;
  modalityHi: string;
}

export interface Identity {
  lagna: SignIdentity;
  moonSign: SignIdentity;
  sunSign: SignIdentity;
  nakshatra: NakshatraIdentity;
  elementModality: ElementModalityPoint[];
}

export type RishiTone = 'direct' | 'traditional' | 'practical' | 'spiritual' | 'analytical' | 'general';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  createdAt: number;
  // Which real specialist Rishi this reply's topic belongs to (see
  // api/client.ts ChatReply) — only ever set on assistant messages, shown
  // as a small corner label so a generalist persona's replies still credit
  // the real specialty behind the answer.
  answeredByRishiId?: string;
}

export interface PassOption {
  id: string;
  durationLabel: Record<Language, string>;
  priceInr: number;
  credits: number;
}

export interface Remedy {
  id: string;
  text: string;
}

export type PreferenceKey = 'family' | 'health' | 'career' | 'marriageRelationships' | 'friends';

export type InsightTone = 'good' | 'average' | 'watch';

export interface Insight {
  id: string;
  preference: PreferenceKey;
  tone: InsightTone;
  title: string;
  message: string;
}

export interface ValidationStatement {
  id: string;
  text: string;
}

