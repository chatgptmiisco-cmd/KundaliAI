// The birth-data form only collects a free-text place name (no map picker),
// but real chart calculation needs latitude/longitude/timezone-offset. This
// is a small offline lookup for major cities rather than a live geocoding
// API call — no network dependency during onboarding (a bad place for a
// flaky external call to fail), no API key needed. Falls back to New Delhi
// (IST) when the text doesn't match anything here.
//
// TODO: replace with a real geocoding service (Google Geocoding API,
// OpenStreetMap Nominatim, etc.) once that's worth the added dependency —
// this table only covers major cities.
interface CityCoordinates {
  latitude: number;
  longitude: number;
  timezoneOffsetHours: number;
}

const CITY_COORDINATES: Record<string, CityCoordinates> = {
  'new delhi': { latitude: 28.6139, longitude: 77.209, timezoneOffsetHours: 5.5 },
  delhi: { latitude: 28.7041, longitude: 77.1025, timezoneOffsetHours: 5.5 },
  mumbai: { latitude: 19.076, longitude: 72.8777, timezoneOffsetHours: 5.5 },
  bombay: { latitude: 19.076, longitude: 72.8777, timezoneOffsetHours: 5.5 },
  pune: { latitude: 18.5204, longitude: 73.8567, timezoneOffsetHours: 5.5 },
  bangalore: { latitude: 12.9716, longitude: 77.5946, timezoneOffsetHours: 5.5 },
  bengaluru: { latitude: 12.9716, longitude: 77.5946, timezoneOffsetHours: 5.5 },
  hyderabad: { latitude: 17.385, longitude: 78.4867, timezoneOffsetHours: 5.5 },
  chennai: { latitude: 13.0827, longitude: 80.2707, timezoneOffsetHours: 5.5 },
  madras: { latitude: 13.0827, longitude: 80.2707, timezoneOffsetHours: 5.5 },
  kolkata: { latitude: 22.5726, longitude: 88.3639, timezoneOffsetHours: 5.5 },
  calcutta: { latitude: 22.5726, longitude: 88.3639, timezoneOffsetHours: 5.5 },
  ahmedabad: { latitude: 23.0225, longitude: 72.5714, timezoneOffsetHours: 5.5 },
  surat: { latitude: 21.1702, longitude: 72.8311, timezoneOffsetHours: 5.5 },
  jaipur: { latitude: 26.9124, longitude: 75.7873, timezoneOffsetHours: 5.5 },
  lucknow: { latitude: 26.8467, longitude: 80.9462, timezoneOffsetHours: 5.5 },
  kanpur: { latitude: 26.4499, longitude: 80.3319, timezoneOffsetHours: 5.5 },
  nagpur: { latitude: 21.1458, longitude: 79.0882, timezoneOffsetHours: 5.5 },
  indore: { latitude: 22.7196, longitude: 75.8577, timezoneOffsetHours: 5.5 },
  bhopal: { latitude: 23.2599, longitude: 77.4126, timezoneOffsetHours: 5.5 },
  patna: { latitude: 25.5941, longitude: 85.1376, timezoneOffsetHours: 5.5 },
  vadodara: { latitude: 22.3072, longitude: 73.1812, timezoneOffsetHours: 5.5 },
  baroda: { latitude: 22.3072, longitude: 73.1812, timezoneOffsetHours: 5.5 },
  ludhiana: { latitude: 30.901, longitude: 75.8573, timezoneOffsetHours: 5.5 },
  agra: { latitude: 27.1767, longitude: 78.0081, timezoneOffsetHours: 5.5 },
  nashik: { latitude: 19.9975, longitude: 73.7898, timezoneOffsetHours: 5.5 },
  varanasi: { latitude: 25.3176, longitude: 82.9739, timezoneOffsetHours: 5.5 },
  chandigarh: { latitude: 30.7333, longitude: 76.7794, timezoneOffsetHours: 5.5 },
  amritsar: { latitude: 31.634, longitude: 74.8723, timezoneOffsetHours: 5.5 },
  coimbatore: { latitude: 11.0168, longitude: 76.9558, timezoneOffsetHours: 5.5 },
  kochi: { latitude: 9.9312, longitude: 76.2673, timezoneOffsetHours: 5.5 },
  cochin: { latitude: 9.9312, longitude: 76.2673, timezoneOffsetHours: 5.5 },
  thiruvananthapuram: { latitude: 8.5241, longitude: 76.9366, timezoneOffsetHours: 5.5 },
  guwahati: { latitude: 26.1445, longitude: 91.7362, timezoneOffsetHours: 5.5 },
  bhubaneswar: { latitude: 20.2961, longitude: 85.8245, timezoneOffsetHours: 5.5 },
  ranchi: { latitude: 23.3441, longitude: 85.3096, timezoneOffsetHours: 5.5 },
  dehradun: { latitude: 30.3165, longitude: 78.0322, timezoneOffsetHours: 5.5 },
  raipur: { latitude: 21.2514, longitude: 81.6296, timezoneOffsetHours: 5.5 },
  // A few common non-India cities for NRI users.
  london: { latitude: 51.5072, longitude: -0.1276, timezoneOffsetHours: 0 },
  'new york': { latitude: 40.7128, longitude: -74.006, timezoneOffsetHours: -5 },
  toronto: { latitude: 43.6532, longitude: -79.3832, timezoneOffsetHours: -5 },
  dubai: { latitude: 25.2048, longitude: 55.2708, timezoneOffsetHours: 4 },
  singapore: { latitude: 1.3521, longitude: 103.8198, timezoneOffsetHours: 8 },
  sydney: { latitude: -33.8688, longitude: 151.2093, timezoneOffsetHours: 10 },
};

const DEFAULT_COORDINATES: CityCoordinates = CITY_COORDINATES['new delhi'];

/** Last-resort fallback only — used when the user never picked a live
 * geocoded suggestion (see searchPlaces below) and typed a place this
 * offline table doesn't recognize. Silently defaulting to New Delhi is a
 * real accuracy risk (a mistyped or unlisted town gets someone else's
 * chart's coordinates with no error shown), which is exactly what live
 * geocoding below exists to avoid — this stays only as a no-network
 * fallback. */
export function resolveBirthPlace(placeText: string): CityCoordinates {
  const firstToken = placeText.split(',')[0]?.trim().toLowerCase() ?? '';
  if (CITY_COORDINATES[firstToken]) {
    return CITY_COORDINATES[firstToken];
  }
  const lowerFull = placeText.toLowerCase();
  const match = Object.keys(CITY_COORDINATES).find((city) => lowerFull.includes(city));
  return match ? CITY_COORDINATES[match] : DEFAULT_COORDINATES;
}

// --- Live place search (OpenStreetMap Nominatim) ---------------------------
// Real geocoding, not just the ~45-city offline table above — a typo or an
// unlisted town used to silently resolve to New Delhi's coordinates with no
// indication anything was wrong. Nominatim is free and needs no API key,
// which matters here since no geocoding provider was configured anywhere in
// this app before; its usage policy just asks for an identifying User-Agent
// and reasonable request volume, both satisfied by debouncing input in the
// UI (see PlaceAutocomplete) rather than firing a request per keystroke.

export interface GeocodeResult {
  displayName: string;
  latitude: number;
  longitude: number;
  timezoneOffsetHours: number;
}

interface NominatimResult {
  display_name: string;
  lat: string;
  lon: string;
  address?: { country_code?: string };
}

// Countries that sit on a single standard UTC offset year-round — safe to
// use directly. Large multi-timezone countries (US, Canada, Australia,
// Russia, Brazil, ...) deliberately aren't listed here since one flat
// offset would be wrong for much of them; those fall through to the
// longitude-based estimate below instead. Real historical DST rules aren't
// modeled either way — this is a best-effort estimate, not an authority.
const COUNTRY_OFFSET_HOURS: Record<string, number> = {
  in: 5.5, pk: 5, bd: 6, np: 5.75, lk: 5.5, mm: 6.5,
  gb: 0, ie: 0, pt: 0,
  fr: 1, de: 1, es: 1, it: 1, nl: 1, be: 1, ch: 1, se: 1, no: 1, dk: 1, pl: 1, at: 1,
  ae: 4, sa: 3, qa: 3, kw: 3, om: 4, il: 2,
  sg: 8, my: 8, hk: 8, tw: 8, ph: 8,
  jp: 9, kr: 9,
  th: 7, vn: 7, id: 7,
  nz: 12,
  za: 2, eg: 2, ke: 3, ng: 1,
};

function estimateTimezoneOffsetHours(countryCode: string | undefined, longitude: number): number {
  const known = countryCode ? COUNTRY_OFFSET_HOURS[countryCode.toLowerCase()] : undefined;
  if (known !== undefined) return known;
  // Rough fallback for anywhere without a known single-zone offset — real
  // timezone boundaries don't track longitude exactly, but this is still
  // far closer than silently defaulting to New Delhi's +5:30.
  return Math.round(longitude / 15);
}

/** Live place search-as-you-type. Returns [] for a too-short query rather
 * than firing a request, and throws on a network/HTTP failure so the caller
 * can fall back to resolveBirthPlace rather than silently showing nothing. */
export async function searchPlaces(query: string): Promise<GeocodeResult[]> {
  const trimmed = query.trim();
  if (trimmed.length < 3) return [];

  const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1&limit=6&q=${encodeURIComponent(trimmed)}`;
  const res = await fetch(url, {
    headers: {
      'User-Agent': 'KundaliAI/1.0 (astrology app birth-place lookup)',
      Accept: 'application/json',
    },
  });
  if (!res.ok) {
    throw new Error(`Place search failed (${res.status})`);
  }
  const results: NominatimResult[] = await res.json();
  return results.map((r) => {
    const longitude = parseFloat(r.lon);
    return {
      displayName: r.display_name,
      latitude: parseFloat(r.lat),
      longitude,
      timezoneOffsetHours: estimateTimezoneOffsetHours(r.address?.country_code, longitude),
    };
  });
}
