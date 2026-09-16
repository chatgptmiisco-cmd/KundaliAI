import { resolveBirthPlace } from '../data/geocoding';
import { apiRequest, setAuthToken } from './httpClient';
import {
  BirthChart,
  BirthData,
  ChartType,
  CurrentDasha,
  DailyReading,
  DashaPeriod,
  Dignity,
  FocusAreaReading,
  GunaMilanResult,
  Identity,
  KundaliComplete,
  KundaliSection,
  KundaliSummary,
  Language,
  ManglikStatus,
  PeriodAnalysis,
  PlanetDetail,
  PlanetKey,
  PreferenceKey,
  ValidationQuestion,
} from '../types/kundali';

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
}

export async function signup(
  email: string,
  password: string,
  name: string,
  language: Language,
): Promise<{ accessToken: string; userId: string }> {
  const res = await apiRequest<TokenResponse>('/auth/signup', {
    method: 'POST',
    auth: false,
    body: { email, password, name, preferred_language: language },
  });
  setAuthToken(res.access_token);
  return { accessToken: res.access_token, userId: res.user_id };
}

export async function login(
  email: string,
  password: string,
): Promise<{ accessToken: string; userId: string }> {
  const res = await apiRequest<TokenResponse>('/auth/login', {
    method: 'POST',
    auth: false,
    body: { email, password },
  });
  setAuthToken(res.access_token);
  return { accessToken: res.access_token, userId: res.user_id };
}

/** No verification step (no OTP/reset link) — anyone who knows the email can
 * reset it. Logs the user in immediately on success, same as signup/login. */
export async function resetPassword(
  email: string,
  newPassword: string,
): Promise<{ accessToken: string; userId: string }> {
  const res = await apiRequest<TokenResponse>('/auth/reset-password', {
    method: 'POST',
    auth: false,
    body: { email, new_password: newPassword },
  });
  setAuthToken(res.access_token);
  return { accessToken: res.access_token, userId: res.user_id };
}

interface RequestOtpResponse {
  phone: string;
  expires_in_seconds: number;
  /** Only present because no real SMS provider is wired up yet — the backend
   * hands the code straight back so phone login is testable without SMS. */
  dev_code: string | null;
}

/** Returns the dev-mode OTP code directly (`devCode`) when the backend has no
 * real SMS provider configured, so the UI can surface it for testing instead
 * of the user needing to receive an actual text message. */
export async function requestOtp(phone: string): Promise<{ expiresInSeconds: number; devCode: string | null }> {
  const res = await apiRequest<RequestOtpResponse>('/auth/otp/request', {
    method: 'POST',
    auth: false,
    body: { phone },
  });
  return { expiresInSeconds: res.expires_in_seconds, devCode: res.dev_code };
}

export async function verifyOtp(
  phone: string,
  code: string,
): Promise<{ accessToken: string; userId: string }> {
  const res = await apiRequest<TokenResponse>('/auth/otp/verify', {
    method: 'POST',
    auth: false,
    body: { phone, code },
  });
  setAuthToken(res.access_token);
  return { accessToken: res.access_token, userId: res.user_id };
}


export function restoreAuthToken(token: string | null) {
  setAuthToken(token);
}

export async function deleteAccount(): Promise<void> {
  await apiRequest<void>('/user/account', { method: 'DELETE' });
  setAuthToken(null);
}

// ---------------------------------------------------------------------------
// Profile — used right after auth to check whether this account already has
// birth data saved (a returning user on a new device/browser), so onboarding
// can be skipped instead of asking them to re-enter everything.
// ---------------------------------------------------------------------------

interface UserProfileApi {
  id: string;
  email: string | null;
  phone: string | null;
  preferred_language: string;
  subscription_tier: string;
  birth_data: {
    name: string;
    date_of_birth: string;
    time_of_birth: string;
    place_of_birth: string;
  } | null;
  preferences: string[];
}

export async function getUserProfile(): Promise<{ birthData: BirthData | null; preferences: PreferenceKey[] }> {
  const data = await apiRequest<UserProfileApi>('/user/profile');
  return {
    birthData: data.birth_data
      ? {
          name: data.birth_data.name,
          dateOfBirth: data.birth_data.date_of_birth,
          timeOfBirth: data.birth_data.time_of_birth,
          placeOfBirth: data.birth_data.place_of_birth,
        }
      : null,
    // Defensive filter (same convention as useUserStore's persisted-state
    // migration) so a preference key from a since-renamed build never
    // reaches an icon/label lookup keyed by the current PreferenceKey union.
    preferences: data.preferences.filter((p): p is PreferenceKey =>
      (['family', 'health', 'career', 'marriageRelationships', 'friends'] as string[]).includes(p),
    ),
  };
}

export async function putPreferences(preferences: PreferenceKey[]): Promise<void> {
  await apiRequest('/user/profile/preferences', {
    method: 'PUT',
    body: { preferences },
  });
}

// ---------------------------------------------------------------------------
// Birth data
// ---------------------------------------------------------------------------

export async function putBirthData(data: BirthData): Promise<void> {
  // A live-geocoded selection (see PlaceAutocomplete) is the real, exact
  // coordinate for the place the user actually picked — prefer it over the
  // offline ~45-city table, which only exists as a fallback for when no
  // live selection was made.
  const coords =
    data.latitude !== undefined && data.longitude !== undefined && data.timezoneOffsetHours !== undefined
      ? { latitude: data.latitude, longitude: data.longitude, timezoneOffsetHours: data.timezoneOffsetHours }
      : resolveBirthPlace(data.placeOfBirth);
  await apiRequest('/user/profile/birth-data', {
    method: 'PUT',
    body: {
      name: data.name,
      date_of_birth: data.dateOfBirth,
      time_of_birth: data.timeOfBirth,
      time_uncertain: false,
      place_of_birth: data.placeOfBirth,
      latitude: coords.latitude,
      longitude: coords.longitude,
      timezone_offset_hours: coords.timezoneOffsetHours,
    },
  });
}

// ---------------------------------------------------------------------------
// Kundali: summary / manglik / complete
// ---------------------------------------------------------------------------

const SECTION_ID_MAP: Record<string, KundaliSection['id']> = {
  personality_nature: 'personalityNature',
  career_money: 'careerMoney',
  relationships_marriage: 'relationshipsMarriage',
  health_temperament: 'healthTemperament',
  strengths_challenges: 'strengthsChallenges',
  timing_overview: 'timingOverview',
};

interface ManglikStatusApi {
  is_manglik: boolean;
  summary: string;
  mars_house_from_lagna: number;
  mars_house_from_moon: number;
  details: string[];
  cancellations: string[];
  relationship_note: string;
}

function adaptManglik(m: ManglikStatusApi): ManglikStatus {
  return {
    isManglik: m.is_manglik,
    summary: m.summary,
    marsHouseFromLagna: m.mars_house_from_lagna,
    marsHouseFromMoon: m.mars_house_from_moon,
    details: m.details,
    cancellations: m.cancellations,
    relationshipNote: m.relationship_note,
  };
}

interface CompleteKundaliApi {
  language: string;
  basic_details: { label: string; value: string }[];
  sections: { id: string; title: string; summary: string; key_points: string[] }[];
  manglik: ManglikStatusApi;
  brutal_truth: string;
  summary: {
    lagna: string;
    moon_sign: string;
    core_strength: string;
    core_challenge: string;
    is_manglik: boolean;
    manglik_one_liner: string;
  };
}

let completeKundaliMemo: Partial<Record<Language, CompleteKundaliApi>> = {};
// fetchSummary and fetchComplete both call this for the same language right
// after onboarding (see useKundaliStore) — without also memoizing the
// in-flight promise, both would see the resolved-only memo above as empty
// and fire a second, redundant real request before the first ever returns.
let completeKundaliInFlight: Partial<Record<Language, Promise<CompleteKundaliApi>>> = {};

async function fetchCompleteKundaliRaw(lang: Language): Promise<CompleteKundaliApi> {
  if (completeKundaliMemo[lang]) return completeKundaliMemo[lang]!;
  if (completeKundaliInFlight[lang]) return completeKundaliInFlight[lang]!;

  const promise = apiRequest<CompleteKundaliApi>('/kundali/complete', {
    query: { language: lang, mode: 'simple' },
  })
    .then((data) => {
      completeKundaliMemo[lang] = data;
      delete completeKundaliInFlight[lang];
      return data;
    })
    .catch((err) => {
      delete completeKundaliInFlight[lang];
      throw err;
    });

  completeKundaliInFlight[lang] = promise;
  return promise;
}

/** Call after birth data changes so the next fetch hits the server again
 * instead of returning a stale in-memory copy. */
export function invalidateKundaliMemo() {
  completeKundaliMemo = {};
  completeKundaliInFlight = {};
}

export async function getKundaliSummary(lang: Language): Promise<KundaliSummary> {
  const data = await fetchCompleteKundaliRaw(lang);
  return {
    lagna: data.summary.lagna,
    moonSign: data.summary.moon_sign,
    coreStrength: data.summary.core_strength,
    coreChallenge: data.summary.core_challenge,
    manglik: { isManglik: data.summary.is_manglik, oneLiner: data.summary.manglik_one_liner },
  };
}

export async function getManglikStatus(lang: Language): Promise<ManglikStatus> {
  const data = await apiRequest<ManglikStatusApi>('/kundali/manglik', { query: { language: lang } });
  return adaptManglik(data);
}

interface ValidationQuestionApi {
  period_start: string;
  period_end: string;
  lord: PlanetKey;
  house: number;
  statement: string;
}

export async function getValidationQuestions(lang: Language): Promise<ValidationQuestion[]> {
  const data = await apiRequest<{ language: string; questions: ValidationQuestionApi[] }>(
    '/kundali/validation-questions',
    { query: { language: lang } },
  );
  return data.questions.map((q) => ({
    periodStart: q.period_start,
    periodEnd: q.period_end,
    lord: q.lord,
    house: q.house,
    statement: q.statement,
  }));
}

interface KootaApi {
  key: string;
  label: string;
  score: number;
  max_score: number;
  summary: string;
}

interface GunaMilanApi {
  language: string;
  your_moon_sign: string;
  your_nakshatra: string;
  partner_moon_sign: string;
  partner_nakshatra: string;
  total_score: number;
  max_total: number;
  kootas: KootaApi[];
  mangal_dosha_mismatch: boolean;
  mangal_dosha_note: string | null;
  verdict: GunaMilanResult['verdict'];
  verdict_message: string;
}

export async function getGunaMilan(partner: BirthData, lang: Language): Promise<GunaMilanResult> {
  const coords =
    partner.latitude !== undefined && partner.longitude !== undefined && partner.timezoneOffsetHours !== undefined
      ? { latitude: partner.latitude, longitude: partner.longitude, timezoneOffsetHours: partner.timezoneOffsetHours }
      : resolveBirthPlace(partner.placeOfBirth);
  const data = await apiRequest<GunaMilanApi>('/kundali/guna-milan', {
    method: 'POST',
    body: {
      partner_name: partner.name,
      partner_date_of_birth: partner.dateOfBirth,
      partner_time_of_birth: partner.timeOfBirth,
      partner_place_of_birth: partner.placeOfBirth,
      partner_latitude: coords.latitude,
      partner_longitude: coords.longitude,
      partner_timezone_offset_hours: coords.timezoneOffsetHours,
      language: lang,
    },
  });
  return {
    yourMoonSign: data.your_moon_sign,
    yourNakshatra: data.your_nakshatra,
    partnerMoonSign: data.partner_moon_sign,
    partnerNakshatra: data.partner_nakshatra,
    totalScore: data.total_score,
    maxTotal: data.max_total,
    kootas: data.kootas.map((k) => ({ key: k.key, label: k.label, score: k.score, maxScore: k.max_score, summary: k.summary })),
    mangalDoshaMismatch: data.mangal_dosha_mismatch,
    mangalDoshaNote: data.mangal_dosha_note,
    verdict: data.verdict,
    verdictMessage: data.verdict_message,
  };
}

export async function postKundaliComplete(lang: Language): Promise<KundaliComplete> {
  const data = await fetchCompleteKundaliRaw(lang);
  return {
    generatedAt: new Date().toISOString(),
    language: lang,
    basicDetails: data.basic_details,
    sections: data.sections.map((s) => ({
      id: SECTION_ID_MAP[s.id] ?? (s.id as KundaliSection['id']),
      title: s.title,
      summary: s.summary,
      keyPoints: s.key_points,
    })),
    manglik: adaptManglik(data.manglik),
    brutalTruth: data.brutal_truth,
  };
}

// ---------------------------------------------------------------------------
// Charts (D1/D9/D10)
// ---------------------------------------------------------------------------

interface PlanetPlacementApi {
  planet: string;
  sign_index: number;
  house: number;
  retrograde: boolean;
  degree_in_sign: number | null;
  degree_display: string | null;
  nakshatra_name_en: string | null;
  nakshatra_name_hi: string | null;
  nakshatra_pada: number | null;
  dignity: Dignity | null;
  combust: boolean | null;
}

interface HouseBreakdownApi {
  house: number;
  sign_name_en: string;
  sign_name_hi: string;
  planets: string[];
  explanation_en: string;
  explanation_hi: string;
}

interface YogaFindingApi {
  key: string;
  name_en: string;
  name_hi: string;
  description_en: string;
  description_hi: string;
}

interface ChartApi {
  chart_type: string;
  lagna_sign_index: number;
  lagna_degree_display: string | null;
  planets: PlanetPlacementApi[];
  summary_en: string;
  summary_hi: string;
  key_points_en: string[];
  key_points_hi: string[];
  house_breakdown: HouseBreakdownApi[];
  yogas: YogaFindingApi[];
}

export async function getChart(type: ChartType, lang: Language): Promise<BirthChart> {
  const path = { D1: '/chart/d1', D9: '/chart/d9', D10: '/chart/d10' }[type];
  const data = await apiRequest<ChartApi>(path);
  const planetSignIndex = Object.fromEntries(
    data.planets.map((p) => [p.planet, p.sign_index]),
  ) as Record<PlanetKey, number>;
  const planetRetrograde = Object.fromEntries(
    data.planets.map((p) => [p.planet, p.retrograde]),
  ) as Partial<Record<PlanetKey, boolean>>;
  const planetDetails = Object.fromEntries(
    data.planets.map((p): [string, PlanetDetail] => [
      p.planet,
      {
        planet: p.planet as PlanetKey,
        signIndex: p.sign_index,
        house: p.house,
        retrograde: p.retrograde,
        degreeInSign: p.degree_in_sign,
        degreeDisplay: p.degree_display,
        nakshatraName: lang === 'hi' ? p.nakshatra_name_hi : p.nakshatra_name_en,
        nakshatraPada: p.nakshatra_pada,
        dignity: p.dignity,
        combust: p.combust,
      },
    ]),
  ) as Partial<Record<PlanetKey, PlanetDetail>>;

  return {
    type,
    lagnaSignIndex: data.lagna_sign_index,
    lagnaDegreeDisplay: data.lagna_degree_display,
    planetSignIndex,
    planetRetrograde,
    planetDetails,
    summary: lang === 'hi' ? data.summary_hi : data.summary_en,
    keyPoints: lang === 'hi' ? data.key_points_hi : data.key_points_en,
    houseBreakdown: data.house_breakdown.map((h) => ({
      house: h.house,
      signNameEn: h.sign_name_en,
      signNameHi: h.sign_name_hi,
      planets: h.planets as PlanetKey[],
      explanationEn: h.explanation_en,
      explanationHi: h.explanation_hi,
    })),
    yogas: data.yogas.map((y) => ({
      key: y.key,
      nameEn: y.name_en,
      nameHi: y.name_hi,
      descriptionEn: y.description_en,
      descriptionHi: y.description_hi,
    })),
  };
}

// ---------------------------------------------------------------------------
// Identity basics — Big Three (Lagna/Moon/Sun), birth Nakshatra, and an
// element/modality breakdown across Lagna + the 9 grahas. Both languages
// come back in one payload (same bilingual-in-one-response convention as
// getChart above), so this is cached once, not per-language.
// ---------------------------------------------------------------------------

interface SignIdentityApi {
  sign_en: string;
  sign_hi: string;
  meaning_en: string;
  meaning_hi: string;
  real_effect_en: string;
  real_effect_hi: string;
}

interface NakshatraIdentityApi {
  name_en: string;
  name_hi: string;
  pada: number;
  lord_en: string;
  lord_hi: string;
  symbol_en: string;
  symbol_hi: string;
  meaning_en: string;
  meaning_hi: string;
}

interface ElementModalityPointApi {
  point_key: string;
  point_label_en: string;
  point_label_hi: string;
  element_en: string;
  element_hi: string;
  modality_en: string;
  modality_hi: string;
}

interface IdentityApi {
  lagna: SignIdentityApi;
  moon_sign: SignIdentityApi;
  sun_sign: SignIdentityApi;
  nakshatra: NakshatraIdentityApi;
  element_modality: ElementModalityPointApi[];
}

function mapSignIdentity(s: SignIdentityApi) {
  return {
    signEn: s.sign_en, signHi: s.sign_hi, meaningEn: s.meaning_en, meaningHi: s.meaning_hi,
    realEffectEn: s.real_effect_en, realEffectHi: s.real_effect_hi,
  };
}

export async function getIdentity(): Promise<Identity> {
  const data = await apiRequest<IdentityApi>('/kundali/identity');
  return {
    lagna: mapSignIdentity(data.lagna),
    moonSign: mapSignIdentity(data.moon_sign),
    sunSign: mapSignIdentity(data.sun_sign),
    nakshatra: {
      nameEn: data.nakshatra.name_en,
      nameHi: data.nakshatra.name_hi,
      pada: data.nakshatra.pada,
      lordEn: data.nakshatra.lord_en,
      lordHi: data.nakshatra.lord_hi,
      symbolEn: data.nakshatra.symbol_en,
      symbolHi: data.nakshatra.symbol_hi,
      meaningEn: data.nakshatra.meaning_en,
      meaningHi: data.nakshatra.meaning_hi,
    },
    elementModality: data.element_modality.map((p) => ({
      pointKey: p.point_key,
      pointLabelEn: p.point_label_en,
      pointLabelHi: p.point_label_hi,
      elementEn: p.element_en,
      elementHi: p.element_hi,
      modalityEn: p.modality_en,
      modalityHi: p.modality_hi,
    })),
  };
}

// ---------------------------------------------------------------------------
// Dasha timeline
// ---------------------------------------------------------------------------

interface AntardashaApi {
  lord: string;
  start: string;
  end: string;
  is_current: boolean;
}

interface MahadashaApi extends AntardashaApi {
  antardashas: AntardashaApi[];
}

interface DashaTimelineApi {
  mahadashas: MahadashaApi[];
}

export async function getDashaTimeline(_lang: Language, _birthDateIso: string): Promise<DashaPeriod[]> {
  const data = await apiRequest<DashaTimelineApi>('/dasha/timeline');
  return data.mahadashas.map((m) => ({
    planet: m.lord as PlanetKey,
    startDate: m.start.slice(0, 10),
    endDate: m.end.slice(0, 10),
    isCurrent: m.is_current,
    subPeriods: m.antardashas.map((a) => ({
      planet: a.lord as PlanetKey,
      startDate: a.start.slice(0, 10),
      endDate: a.end.slice(0, 10),
      isCurrent: a.is_current,
    })),
  }));
}

// ---------------------------------------------------------------------------
// Current dasha — the full three-level stack (Mahadasha > Antardasha >
// Pratyantardasha) active right now, at the day's own resolution.
// ---------------------------------------------------------------------------

interface CurrentDashaLevelApi {
  lord: string;
  start: string;
  end: string;
}

interface CurrentDashaApi {
  mahadasha: CurrentDashaLevelApi;
  antardasha: CurrentDashaLevelApi;
  pratyantardasha: CurrentDashaLevelApi;
}

export async function getCurrentDasha(): Promise<CurrentDasha> {
  const data = await apiRequest<CurrentDashaApi>('/dasha/current');
  const level = (l: CurrentDashaLevelApi) => ({
    planet: l.lord as PlanetKey,
    startDate: l.start.slice(0, 10),
    endDate: l.end.slice(0, 10),
  });
  return {
    mahadasha: level(data.mahadasha),
    antardasha: level(data.antardasha),
    pratyantardasha: level(data.pratyantardasha),
  };
}

// ---------------------------------------------------------------------------
// Period analysis — real rating/theme/risks/opportunities for any date range,
// used both for the running period and any historical Dasha period on demand.
// ---------------------------------------------------------------------------

interface PeriodAnalysisApi {
  rating: number;
  theme: string;
  risks: string[];
  opportunities: string[];
  summary: string;
  remaining_free_analyses_this_month: number | null;
}

export async function getPeriodAnalysis(
  startDate: string,
  endDate: string,
  lang: Language,
): Promise<PeriodAnalysis> {
  const data = await apiRequest<PeriodAnalysisApi>('/analysis/period', {
    method: 'POST',
    body: { start_date: startDate, end_date: endDate, language: lang, mode: 'simple' },
  });
  return {
    rating: data.rating,
    theme: data.theme,
    risks: data.risks,
    opportunities: data.opportunities,
    summary: data.summary,
    remainingFreeAnalysesThisMonth: data.remaining_free_analyses_this_month,
  };
}

// ---------------------------------------------------------------------------
// Daily reading — the full "today" engine output (rating, theme, doshas,
// panchang, etc.), all backend-calculated.
// ---------------------------------------------------------------------------

interface DailyReadingApi {
  date: string;
  rating: number;
  rating_reason: string;
  dominant_theme: string;
  energy_mode: string;
  key_risk: string;
  key_opportunity: string;
  brutal_truth: string;
  mahadasha_label: string;
  period_rating: number;
  period_type: string;
  dominant_life_area: string;
  core_strength: string;
  core_weakness: string;
  stress_pattern: string;
  decision_style: string;
  moon_nakshatra: string;
  moon_mood_tag: string;
  transit_highlight: string;
  before_you_leave_home: string[];
  life_growth_task: string;
  tithi_tag: string;
  tithi_name: string;
  paksha: string;
  lunar_month: string;
  festival: string | null;
  today_color: string;
  lucky_number: number;
  today_guidance: string[];
  doshas: { key: string; label: string; is_present: boolean }[];
  jupiter_transiting_moon_sign: boolean;
}

export async function getDailyReading(lang: Language): Promise<DailyReading> {
  const data = await apiRequest<DailyReadingApi>('/kundali/daily-reading', { query: { language: lang } });
  return {
    date: data.date,
    rating: data.rating,
    ratingReason: data.rating_reason,
    dominantTheme: data.dominant_theme,
    energyMode: data.energy_mode,
    keyRisk: data.key_risk,
    keyOpportunity: data.key_opportunity,
    brutalTruth: data.brutal_truth,
    mahadashaLabel: data.mahadasha_label,
    periodRating: data.period_rating,
    periodType: data.period_type,
    dominantLifeArea: data.dominant_life_area,
    coreStrength: data.core_strength,
    coreWeakness: data.core_weakness,
    stressPattern: data.stress_pattern,
    decisionStyle: data.decision_style,
    moonNakshatra: data.moon_nakshatra,
    moonMoodTag: data.moon_mood_tag,
    transitHighlight: data.transit_highlight,
    beforeYouLeaveHome: data.before_you_leave_home,
    lifeGrowthTask: data.life_growth_task,
    tithiTag: data.tithi_tag,
    tithiName: data.tithi_name,
    paksha: data.paksha,
    lunarMonth: data.lunar_month,
    festival: data.festival,
    todayColor: data.today_color,
    luckyNumber: data.lucky_number,
    todayGuidance: data.today_guidance,
    doshas: data.doshas.map((d) => ({ key: d.key, label: d.label, isPresent: d.is_present })),
    jupiterTransitingMoonSign: data.jupiter_transiting_moon_sign,
  };
}

// ---------------------------------------------------------------------------
// Focus-area readings — "how is today for family/health/career/marriage/
// friends", one per area the user chose to follow during onboarding.
// ---------------------------------------------------------------------------

interface FocusAreaReadingApi {
  area: string;
  house: number;
  house_lord: string;
  house_lord_house: number;
  dignity: Dignity;
  rating: number;
  theme: string;
  summary: string;
  meaning: string;
  avoid_today: string;
  focus_today: string;
  transit_note: string | null;
}

interface FocusReadingsApi {
  date: string;
  readings: FocusAreaReadingApi[];
}

export async function getFocusReadings(lang: Language): Promise<FocusAreaReading[]> {
  const data = await apiRequest<FocusReadingsApi>('/kundali/focus-readings', { query: { language: lang } });
  return data.readings.map((r) => ({
    area: r.area,
    house: r.house,
    houseLord: r.house_lord as PlanetKey,
    houseLordHouse: r.house_lord_house,
    dignity: r.dignity,
    rating: r.rating,
    theme: r.theme,
    summary: r.summary,
    meaning: r.meaning,
    avoidToday: r.avoid_today,
    focusToday: r.focus_today,
    transitNote: r.transit_note,
  }));
}

// ---------------------------------------------------------------------------
// Subscription
// ---------------------------------------------------------------------------

export interface SubscriptionApi {
  tier: 'free' | 'insight' | 'strategy';
  status: string;
  billing_cycle: string | null;
  current_period_end: string | null;
}

export async function getSubscription(): Promise<SubscriptionApi> {
  return apiRequest<SubscriptionApi>('/subscription');
}

export async function checkoutSubscription(
  tier: 'insight' | 'strategy',
  billingCycle: 'monthly' | 'yearly' = 'monthly',
): Promise<{ simulated: boolean; note: string }> {
  return apiRequest('/subscription/checkout', {
    method: 'POST',
    body: { tier, billing_cycle: billingCycle },
  });
}

// ---------------------------------------------------------------------------
// Chat (Strategy tier only on the backend — see RishiChatScreen for the
// credit-based fallback used below Strategy)
// ---------------------------------------------------------------------------

export interface ChatReply {
  reply: string;
  // Which real specialist Rishi classically owns this message's topic —
  // independent of which persona is actually chatting (see the backend's
  // detect_answering_rishi) — used to render a small "answered by X" label,
  // most useful when talking to the generalist "vyasa" persona. Undefined
  // when the message didn't match a known category.
  answeredByRishiId?: string;
}

export async function postChatMessage(message: string, lang: Language, rishiId: string): Promise<ChatReply> {
  const res = await apiRequest<{ reply: string; answered_by_rishi_id: string | null }>('/chat/astro', {
    method: 'POST',
    body: { message, language: lang, rishi_id: rishiId },
  });
  return { reply: res.reply, answeredByRishiId: res.answered_by_rishi_id ?? undefined };
}

