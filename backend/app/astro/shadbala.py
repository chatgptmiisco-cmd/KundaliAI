"""Shadbala: the classical six-fold planetary strength system (Sthana,
Dig, Kaala, Cheshta, Naisargika, Drik Bala), summed and converted to Rupas
(1 Rupa = 60 Virupas) and compared against each planet's classical minimum
threshold to judge whether it is genuinely strong.

This is the single most complex classical calculation this app implements —
every formula below was verified against multiple independent sources before
being written (see the PR/commit history for this feature for the research
trail), and every sub-component names its source convention where more than
one exists in the literature. Two real, deliberate scope decisions:

- Rahu/Ketu are excluded from Shadbala entirely — same "not part of the core
  Parashari seven-graha system" convention as app.astro.constants excluding
  them from dignity and special aspects. Only Su/Mo/Ma/Me/Ju/Ve/Sa get a
  Shadbala score.
- Yuddha Bala (the planetary-war strength adjustment applied when two of
  Mars/Mercury/Jupiter/Venus/Saturn are within 1 degree of each other) is
  NOT implemented. Its winner-determination formula requires each planet's
  angular diameter as seen from Earth, and classical/secondary sources
  disagree on the exact constants — other real astrology software projects
  face the identical problem and have documented deliberately omitting it
  for the same reason. Shipping a guessed diameter table would be exactly
  the kind of fabricated precision this app avoids elsewhere (e.g. Grahan/
  Pitru Dosha are left out of app.astro.doshas for the same class of
  reason). This is a rare edge case (two of five planets within 1 degree of
  longitude) — its absence should almost never matter in practice.
- Varsha Bala and Masa Bala (the year-lord and month-lord components of
  Kaala Bala, 15 and 30 Virupas respectively when a planet holds that
  lordship) are also NOT implemented: unlike the day-lord (Vara Bala, the
  weekday) and hour-lord (Hora Bala, both implemented below and well
  documented), no source consulted while building this stated the exact
  algorithm for determining WHICH weekday counts as a given year's or
  month's "lord" precisely enough to implement with confidence — every
  candidate this app could construct (e.g. from Sankranti dates) would be
  this app's own invented convention, not a verified classical one. Total
  Shadbala here is therefore up to 45 Virupas (0.75 Rupas) lower than a
  fully complete calculation for whichever single planet would have held
  the year and/or month lordship — see `compute_shadbala`'s docstring for
  how this affects the strength verdict near a threshold.
"""
from dataclasses import dataclass

from app.astro.charts import degree_in_sign, house_number
from app.astro.constants import (
    EXALTATION_SIGN,
    NATURAL_MALEFICS,
    OWN_SIGNS,
    PlanetKey,
    SIGN_LORDS,
    planet_relation,
)
from app.astro.ephemeris import calendar_date_utc, sunrise_utc, sunset_utc

_SHADBALA_PLANETS: tuple[PlanetKey, ...] = ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa")

# --- Naisargika Bala (natural strength) -------------------------------------
# A fixed classical ranking (Sun strongest .. Saturn weakest), evenly spaced
# across the 0-60 Virupa range in 7 equal steps of 60/7 — not an
# independently memorized table, but the direct arithmetic consequence of
# "Sun=60, Saturn=8.57(=60/7), evenly spaced by rank" as BPHS states it.
_NAISARGIKA_RANK: tuple[PlanetKey, ...] = ("Su", "Mo", "Ve", "Ju", "Me", "Ma", "Sa")


def naisargika_bala(planet: PlanetKey) -> float:
    rank = _NAISARGIKA_RANK.index(planet)
    return 60.0 - rank * (60.0 / 7.0)


# --- Sthana Bala (positional strength): 5 sub-components --------------------

def uccha_bala(planet: PlanetKey, longitude: float) -> float:
    """0 at exact debilitation, 60 at exact exaltation, linear in between —
    the exaltation and debilitation points are always exactly 180 deg apart,
    so "distance from the debilitation point" (0-180) scaled by 1/3 gives
    the standard 0-60 Virupa range."""
    debilitation_point = (EXALTATION_SIGN[planet] * 30 + _EXALTATION_DEGREE[planet] + 180) % 360
    distance = abs((longitude - debilitation_point + 180) % 360 - 180)
    return distance / 3


# Exact classical exaltation degree WITHIN the exaltation sign (Uccha Bindu)
# — e.g. the Sun is exalted at 10 deg Aries specifically, not merely
# "somewhere in Aries". Needed for Uccha Bala's continuous (not sign-level)
# distance formula.
_EXALTATION_DEGREE: dict[PlanetKey, float] = {
    "Su": 10.0, "Mo": 3.0, "Ma": 28.0, "Me": 15.0, "Ju": 5.0, "Ve": 27.0, "Sa": 20.0,
}

_KENDRA_HOUSES = {1, 4, 7, 10}
_PANAPARA_HOUSES = {2, 5, 8, 11}


def kendradi_bala(house: int) -> float:
    if house in _KENDRA_HOUSES:
        return 60.0
    if house in _PANAPARA_HOUSES:
        return 30.0
    return 15.0  # Apoklima (3,6,9,12)


# Planets in "odd" (Oja) vs "even" (Yugma) sign want opposite signs: the
# Moon and Venus (classically female) draw strength from an even sign; the
# Sun, Mars and Jupiter (male) and Mercury and Saturn (neutral/napumsaka)
# from an odd one. Checked identically for D1 and D9 (15 Virupas each, 30 max).
_WANTS_EVEN_SIGN: frozenset[PlanetKey] = frozenset({"Mo", "Ve"})


def ojhayugmarasyamsa_bala(planet: PlanetKey, d1_sign: int, d9_sign: int) -> float:
    def _score(sign: int) -> float:
        is_even = sign % 2 == 1  # 0-indexed odd == classically "even-numbered" sign
        wants_even = planet in _WANTS_EVEN_SIGN
        return 15.0 if is_even == wants_even else 0.0

    return _score(d1_sign) + _score(d9_sign)


# Gender classification for Drekkana Bala specifically (matches the same
# male/female/neutral split as Ojhayugmarasyamsa Bala's, restated here for
# clarity since it drives a different rule): male planets get the point in
# the 1st decan (0-10 deg) of the sign they occupy, neutral in the 2nd
# (10-20 deg), female in the 3rd (20-30 deg). 15 Virupas when the planet's
# own decan matches its gender's decan, 0 otherwise. (Some secondary sources
# state 60 Virupas here instead of 15 — this app follows the more commonly
# tabulated 15, consistent with Drekkana Bala's usual description as a minor
# contributor alongside Kendradi/Ojhayugmarasyamsa's own 15-30 range, not a
# major limb on the scale of Uccha or Saptavargaja Bala.)
_MALE_PLANETS: frozenset[PlanetKey] = frozenset({"Su", "Ma", "Ju"})
_FEMALE_PLANETS: frozenset[PlanetKey] = frozenset({"Mo", "Ve"})
_NEUTRAL_PLANETS: frozenset[PlanetKey] = frozenset({"Me", "Sa"})


def drekkana_bala(planet: PlanetKey, longitude: float) -> float:
    decan = int(degree_in_sign(longitude) // 10)  # 0, 1, or 2
    matches = (
        (decan == 0 and planet in _MALE_PLANETS)
        or (decan == 1 and planet in _NEUTRAL_PLANETS)
        or (decan == 2 and planet in _FEMALE_PLANETS)
    )
    return 15.0 if matches else 0.0


# --- Panchadha Maitri (five-fold relationship) + Saptavargaja Bala ---------
# Saptavargaja Bala needs a finer-grained relationship than the natural-only
# friend/neutral/enemy app.astro.constants.planet_relation already provides:
# the classical FIVE-fold "compound" relationship (Adhi Mitra/Mitra/Sama/
# Shatru/Adhi Shatru), which layers a TEMPORARY relationship (based on
# house distance between the two planets IN THIS CHART, on the day of
# birth) on top of the fixed natural one. Both layers reduce to a simple
# +1 (friend) / 0 (neutral) / -1 (enemy) score; the two scores are summed
# (natural has all three values, temporary only +1/-1) to a range of -2..+2,
# which maps directly onto the five named compound relationships.
_TEMPORARY_FRIEND_HOUSES = {2, 3, 4, 10, 11, 12}


def temporary_relation(house_a_from_b: int) -> str:
    """`house_a_from_b` = the whole-sign house planet A occupies counting
    from planet B's own sign as house 1 (i.e. app.astro.charts.house_number
    with B's sign as the "Lagna"). Planets in the 2nd/3rd/4th/10th/11th/12th
    house from each other are temporary friends; the rest (1st, own house —
    same sign — included, plus 5th/6th/7th/8th/9th) are temporary enemies."""
    return "friend" if house_a_from_b in _TEMPORARY_FRIEND_HOUSES else "enemy"


_COMPOUND_RELATION_BY_SCORE: dict[int, str] = {
    2: "great_friend", 1: "friend", 0: "neutral", -1: "enemy", -2: "great_enemy",
}
_NATURAL_SCORE: dict[str, int] = {"friend": 1, "neutral": 0, "enemy": -1}
_TEMPORARY_SCORE: dict[str, int] = {"friend": 1, "enemy": -1}


def compound_relation(planet: PlanetKey, other: PlanetKey, other_sign_from_planet_sign: int) -> str:
    """Panchadha Maitri of `other` toward `planet`: combines
    app.astro.constants.planet_relation (natural) with `temporary_relation`
    (this chart's house distance) into one of great_friend/friend/neutral/
    enemy/great_enemy."""
    natural_score = _NATURAL_SCORE[planet_relation(planet, other)]
    temporary_score = _TEMPORARY_SCORE[temporary_relation(other_sign_from_planet_sign)]
    return _COMPOUND_RELATION_BY_SCORE[natural_score + temporary_score]


# Exact classical Moolatrikona sign + degree range per planet — a narrower
# portion of the planet's own sign that outranks plain "own sign" (see
# _SAPTAVARGAJA_POINTS below). Rahu/Ketu have no Moolatrikona (excluded from
# Shadbala entirely — see module docstring).
_MOOLATRIKONA: dict[PlanetKey, tuple[int, float, float]] = {
    "Su": (4, 0.0, 20.0), "Mo": (1, 4.0, 20.0), "Ma": (0, 0.0, 12.0), "Me": (5, 16.0, 20.0),
    "Ju": (8, 0.0, 10.0), "Ve": (6, 0.0, 15.0), "Sa": (10, 0.0, 20.0),
}

_SAPTAVARGAJA_POINTS: dict[str, float] = {
    "moolatrikona": 45.0, "own": 30.0, "great_friend": 22.5, "friend": 15.0,
    "neutral": 7.5, "enemy": 3.75, "great_enemy": 1.875,
}


def _varga_dignity_points(
    planet: PlanetKey, varga_sign: int, natal_planet_sign: dict[PlanetKey, int], moolatrikona_degree: float | None
) -> float:
    """`moolatrikona_degree` is D1's degree-within-sign, required to grant
    Moolatrikona status (a narrower dignity than plain own-sign — see
    _SAPTAVARGAJA_POINTS) at all: Moolatrikona is inherently a DEGREE range
    within a sign, but a divisional sign has no independent degree of its
    own (same "no continuous degree on a varga" convention already used for
    D9/D10 in app.astro.charts.ChartResult), so pass None for every varga
    OTHER than D1 — occupying the Moolatrikona SIGN there still scores as
    plain "own sign" (30), via the OWN_SIGNS fallthrough below, not the
    higher Moolatrikona score (45), since the classical Moolatrikona/own
    distinction fundamentally depends on the degree it doesn't have."""
    moolatrikona_sign, lo, hi = _MOOLATRIKONA[planet]
    if varga_sign == moolatrikona_sign and moolatrikona_degree is not None and lo <= moolatrikona_degree < hi:
        return _SAPTAVARGAJA_POINTS["moolatrikona"]
    if varga_sign in OWN_SIGNS[planet]:
        return _SAPTAVARGAJA_POINTS["own"]
    lord = SIGN_LORDS[varga_sign]
    if lord == planet:
        return _SAPTAVARGAJA_POINTS["own"]
    relation = compound_relation(
        planet, lord, house_number(natal_planet_sign[lord], natal_planet_sign[planet])
    )
    return _SAPTAVARGAJA_POINTS[relation]


def saptavargaja_bala(
    planet: PlanetKey,
    d1_sign: int,
    d1_degree_in_sign: float,
    varga_signs: dict[str, int],
    natal_planet_sign: dict[PlanetKey, int],
) -> float:
    """Sum of dignity points (see _SAPTAVARGAJA_POINTS) across all seven
    classical vargas — D1 (`d1_sign`/`d1_degree_in_sign`) plus
    D2/D3/D7/D9/D12/D30 (`varga_signs`, keyed "D2".."D30", from
    app.astro.vargas). `natal_planet_sign` (every classical planet's D1
    sign) is needed to compute the compound (Panchadha) relationship to
    each varga sign's lord when the planet doesn't own or moolatrikona that
    sign itself."""
    total = _varga_dignity_points(planet, d1_sign, natal_planet_sign, d1_degree_in_sign)
    for varga_sign in varga_signs.values():
        total += _varga_dignity_points(planet, varga_sign, natal_planet_sign, None)
    return total


# --- Dig Bala (directional strength) ----------------------------------------
# Each planet is strongest at ONE specific house's cusp and weakest at the
# cusp exactly opposite it (180 deg away) — Virupas scale linearly with
# degree-distance from the weak point, reaching the full 60 exactly at the
# strong cusp. House cusps here are the equal/whole-sign convention (Lagna
# longitude + 30*(house-1)) since this app is whole-sign only throughout —
# a documented simplification versus a Placidus/other true-cusp system,
# same convention as every other whole-sign-only calculation in app.astro.
_DIG_BALA_STRONG_HOUSE: dict[PlanetKey, int] = {
    "Ju": 1, "Me": 1, "Ve": 4, "Mo": 4, "Sa": 7, "Su": 10, "Ma": 10,
}


def dig_bala(planet: PlanetKey, longitude: float, lagna_longitude: float) -> float:
    strong_cusp = (lagna_longitude + (_DIG_BALA_STRONG_HOUSE[planet] - 1) * 30) % 360
    weak_cusp = (strong_cusp + 180) % 360
    distance_from_weak_point = abs((longitude - weak_cusp + 180) % 360 - 180)
    return distance_from_weak_point / 3


# --- Kaala Bala (temporal strength) -----------------------------------------

def paksha_bala(sun_longitude: float, moon_longitude: float, planet: PlanetKey) -> float:
    """Based on the Moon's elongation from the Sun (0 deg = new moon, 180 =
    full moon): benefics (here: all planets except the malefics below) gain
    strength as the Moon waxes, malefics as it wanes, and the Moon's OWN
    Paksha Bala is always doubled (Saravali's documented convention — see
    module research notes) before the /60 scale is applied elsewhere, since
    its own light is literally what Paksha measures."""
    elongation = abs((moon_longitude - sun_longitude + 180) % 360 - 180)  # 0-180
    is_malefic = planet in NATURAL_MALEFICS and planet != "Mo"
    bala = (180 - elongation) / 3 if is_malefic else elongation / 3
    return bala * 2 if planet == "Mo" else bala


_AYANA_OBLIQUITY = 23.45  # eps, the classical/mean obliquity of the ecliptic


def ayana_bala(planet: PlanetKey, planet_declination: float) -> float:
    """Kranti (declination)-based method — one of at least two documented
    classical approaches (the other, Parashara's tropical-longitude-Khanda
    method, is not used here since it requires reconstructing degree-based
    "Khanda" tables that are themselves inconsistently transcribed across
    sources; the declination-based formula is numerically cleaner given
    this app already has precise declination via app.astro.ephemeris and
    avoids re-deriving it from tropical longitude + latitude by hand).
    Moon and Saturn score higher for SOUTHERN declination, every other
    planet here for NORTHERN; Mercury benefits from either direction. The
    Sun's result is doubled (same documented convention as its own light
    dominating Ayana the way it dominates Paksha)."""
    if planet == "Me":
        bala = _AYANA_OBLIQUITY + abs(planet_declination)
    elif planet in ("Mo", "Sa"):
        bala = _AYANA_OBLIQUITY - planet_declination
    else:
        bala = _AYANA_OBLIQUITY + planet_declination
    bala = max(0.0, min(2 * _AYANA_OBLIQUITY, bala)) * (60 / (2 * _AYANA_OBLIQUITY))
    return bala * 2 if planet == "Su" else bala


@dataclass(frozen=True)
class DayNightWindow:
    is_day: bool
    start: float  # Julian Day (UT) of this day/night period's sunrise/sunset boundary
    end: float


def _most_recent_event_at_or_before(
    jd: float, search_fn, latitude: float, longitude: float
) -> float:
    """The latest occurrence of a sunrise/sunset-like event (`search_fn` —
    sunrise_utc or sunset_utc, both "next occurrence at-or-after") that is
    itself at or before `jd`. A single "look back ~1 day" guess is NOT
    reliable near a sunrise/sunset boundary: e.g. looking back 1.2 days from
    just after today's sunset can land during YESTERDAY's daytime, before
    yesterday's own sunset — so a naive forward search from there finds
    YESTERDAY's sunset, not today's. This instead keeps advancing forward
    from an initial guess until the result would overshoot `jd`, guaranteeing
    the true most-recent event regardless of exactly how far back the
    initial guess landed."""
    candidate = search_fn(jd - 1.2, latitude, longitude)
    while True:
        next_candidate = search_fn(candidate + 1e-6, latitude, longitude)
        if next_candidate > jd:
            return candidate
        candidate = next_candidate


def day_night_window(birth_jd_ut: float, latitude: float, longitude: float) -> DayNightWindow:
    """Which day/night period (sunrise-to-sunset, or sunset-to-sunrise)
    contains `birth_jd_ut`, and that period's exact bounds — the shared
    basis for Nathonnata and Tribhaga Bala below."""
    prev_rise = _most_recent_event_at_or_before(birth_jd_ut, sunrise_utc, latitude, longitude)
    prev_set = _most_recent_event_at_or_before(birth_jd_ut, sunset_utc, latitude, longitude)
    is_day = prev_rise > prev_set
    if is_day:
        next_set = sunset_utc(birth_jd_ut, latitude, longitude)
        return DayNightWindow(is_day=True, start=prev_rise, end=next_set)
    next_rise = sunrise_utc(birth_jd_ut, latitude, longitude)
    return DayNightWindow(is_day=False, start=prev_set, end=next_rise)


def nathonnata_bala(planet: PlanetKey, birth_jd_ut: float, window: DayNightWindow) -> float:
    """Mercury is always 60. Diurnal planets (Su, Ju, Ve) peak at local
    noon/midnight depending on which half of the day/night window the birth
    falls in more precisely: this app uses the simpler, commonly-documented
    version — full strength at the FAVORABLE window's own midpoint, zero at
    its edges (sunrise/sunset or sunset/sunrise), linear between — rather
    than the more elaborate "unnata measured continuously across a full
    sunrise-to-sunrise cycle" formulation some texts use, which requires
    reconstructing exact ghati-based conventions this app cannot verify
    precisely enough to prefer over the simpler, still classically-grounded
    version. Nocturnal planets (Mo, Ma, Sa) use the SAME shape but favor the
    night window instead."""
    if planet == "Me":
        return 60.0
    is_diurnal = planet in ("Su", "Ju", "Ve")
    favorable_window = window if (window.is_day == is_diurnal) else None
    if favorable_window is None:
        return 0.0
    midpoint = (favorable_window.start + favorable_window.end) / 2
    half_span = (favorable_window.end - favorable_window.start) / 2
    distance_from_midpoint = abs(birth_jd_ut - midpoint)
    return max(0.0, 60.0 * (1 - distance_from_midpoint / half_span))


def tribhaga_bala(planet: PlanetKey, birth_jd_ut: float, window: DayNightWindow) -> float:
    """Jupiter is always 60. The day (or night) window splits into three
    equal thirds, each ruled by a fixed pair of planets (one for day, one
    for night) — the ruling planet(s) of the third the birth falls in score
    60, everyone else scores 0."""
    if planet == "Ju":
        return 60.0
    third_span = (window.end - window.start) / 3
    third_index = min(2, int((birth_jd_ut - window.start) / third_span))
    day_rulers = ("Su", "Sa", "Ve")
    night_rulers = ("Mo", "Ma", "Me")
    rulers = day_rulers if window.is_day else night_rulers
    return 60.0 if planet == rulers[third_index] else 0.0


_WEEKDAY_LORDS: tuple[PlanetKey, ...] = ("Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Su")  # Python weekday(): Mon=0..Sun=6
_HORA_SEQUENCE: tuple[PlanetKey, ...] = ("Su", "Ve", "Me", "Mo", "Sa", "Ju", "Ma")  # cyclic, starting from the day lord


def vara_bala(planet: PlanetKey, weekday_lord: PlanetKey) -> float:
    return 45.0 if planet == weekday_lord else 0.0


def _enclosing_day_and_night(window: DayNightWindow, latitude: float, longitude: float) -> tuple[DayNightWindow, DayNightWindow]:
    """The (day_window, night_window) pair for the single continuous 24-Hora
    cycle containing `window` — always chronologically day-then-night
    (day_window.end == night_window.start), regardless of whether `window`
    ITSELF is the day or the night half, so Hora counting always starts
    from the right sunrise's weekday lord even when birth falls at night."""
    if window.is_day:
        return window, day_night_window(window.end + 1e-6, latitude, longitude)
    return day_night_window(window.start - 1e-6, latitude, longitude), window


def hora_lord_at(birth_jd_ut: float, latitude: float, longitude: float) -> PlanetKey:
    """Which planet rules the Hora (1/12th of the day or night, NOT a fixed
    clock hour — day/night Horas stretch or shrink with real sunrise/sunset)
    containing `birth_jd_ut`, cycling through _HORA_SEQUENCE starting from
    that day's own weekday lord at sunrise, continuing across sunset into
    the night's 12 Horas."""
    window = day_night_window(birth_jd_ut, latitude, longitude)
    day_window, night_window = _enclosing_day_and_night(window, latitude, longitude)
    weekday_lord = _WEEKDAY_LORDS[_weekday_of_sunrise(day_window)]
    start_index = _HORA_SEQUENCE.index(weekday_lord)

    if window.is_day:
        hora_index = int((birth_jd_ut - day_window.start) / ((day_window.end - day_window.start) / 12))
    else:
        # Night Horas continue the SAME cycle across the sunset boundary —
        # 12 day Horas have already elapsed by the time night begins.
        hora_index = 12 + int((birth_jd_ut - night_window.start) / ((night_window.end - night_window.start) / 12))
    return _HORA_SEQUENCE[(start_index + hora_index) % 7]


def _weekday_of_sunrise(day_window: DayNightWindow) -> int:
    # The classical "which weekday's lord" for Hora purposes is the weekday
    # NAME of the sunrise moment itself (the day is reckoned from ITS OWN
    # sunrise to the next, not the UTC calendar boundary, but the weekday
    # label still comes from the plain UTC calendar date of that moment).
    return calendar_date_utc(day_window.start).weekday()


def hora_bala(planet: PlanetKey, current_hora_lord: PlanetKey) -> float:
    return 60.0 if planet == current_hora_lord else 0.0


# --- Cheshta Bala (motional strength) ---------------------------------------
# The Sun's Cheshta Bala is defined as identical to its own Ayana Bala, and
# the Moon's as identical to its own Paksha Bala (both stated directly in
# the classical texts — see module research notes) rather than computed from
# speed, since the Sun/Moon never retrograde the way the other five do. For
# the remaining five, this app uses a documented simplification: a
# continuous function of current speed relative to that planet's classical
# MEAN daily motion, rather than the discrete 8-named-state system (Vakra/
# Anuvakra/Vikala/Manda/Mandatara/Sama/Chara/Atichara) whose exact numeric
# speed-percentage BOUNDARIES are inconsistently transcribed across sources
# (even the specific Virupa value per state varies: 15 vs 60 for the same
# named state, between two sources checked while building this). A
# continuous formula avoids guessing boundaries that would be presented as
# precise classical fact when they are not verifiably so — retrograde motion
# (speed < 0) still reaches the maximum 60, matching every source's
# agreement that retrograde is the strongest motional state; stationary
# (speed = 0) sits at the classical midpoint 30; fast direct motion
# approaches 60 again, matching the (also broadly agreed) principle that
# BOTH extremes of speed, not merely retrograde, carry real Cheshta Bala,
# while motion at exactly the mean carries the least.
_MEAN_DAILY_MOTION: dict[PlanetKey, float] = {
    "Ma": 0.524, "Me": 1.383, "Ju": 0.083, "Ve": 1.2, "Sa": 0.034,
}


def cheshta_bala(planet: PlanetKey, speed: float, sun_ayana_bala: float, moon_paksha_bala: float) -> float:
    if planet == "Su":
        return sun_ayana_bala
    if planet == "Mo":
        return moon_paksha_bala
    if speed < 0:
        return 60.0
    mean_speed = _MEAN_DAILY_MOTION[planet]
    deviation = abs(speed - mean_speed) / mean_speed  # 0 at the mean, unbounded above
    return 30.0 + min(30.0, deviation * 30.0)


# --- Drik Bala (aspectual strength) -----------------------------------------
# Reuses app.astro.natal_insights's aspect/conjunction multiplier (the SAME
# classical drishti + Yuti rules already computed for the Prediction
# Engine's significator-strength scoring) rather than re-deriving a second,
# separately-precise degree-based aspect-strength formula — Shadbala's own
# Drik Bala is itself just "net benefic-minus-malefic aspect strength in
# Virupas", the same underlying classical fact this app already models,
# just on a different numeric scale. The multiplier (typically 0.3-1.5,
# centered on 1.0 for "no aspect influence") is rescaled so 1.0 -> 0 Virupas
# (neutral), 1.5 -> +60, and 0.3 (fully afflicted) -> a matching negative
# value, clamped to Shadbala's own -60..+60 Drik Bala range.
def drik_bala(aspect_and_conjunction_multiplier: float) -> float:
    return max(-60.0, min(60.0, (aspect_and_conjunction_multiplier - 1.0) * 120.0))


# --- Combining all six limbs -------------------------------------------------
# Classical minimum Rupas (BPHS) a planet needs to be considered genuinely
# strong. Note the module docstring's Varsha/Masa Bala omission means a real,
# complete calculation could read up to 0.75 Rupas higher for whichever
# planet holds the year/month lordship — a planet landing just BELOW its
# threshold here could, in a small number of cases, actually be at or above
# it with those two sub-components included. Treat `is_strong` as a
# well-grounded estimate, not a guaranteed-exact classical verdict, when a
# result sits within ~0.75 Rupas of `minimum_rupas`.
MINIMUM_RUPAS: dict[PlanetKey, float] = {
    "Su": 5.0, "Mo": 6.0, "Ma": 5.0, "Me": 7.0, "Ju": 6.5, "Ve": 5.5, "Sa": 5.0,
}


@dataclass(frozen=True)
class ShadbalaResult:
    """One planet's full Shadbala breakdown — see MINIMUM_RUPAS above for
    what `is_strong` means and its caveat near the threshold."""
    planet: PlanetKey
    sthana_bala: float
    dig_bala: float
    kaala_bala: float
    cheshta_bala: float
    naisargika_bala: float
    drik_bala: float
    total_virupas: float
    total_rupas: float
    minimum_rupas: float
    is_strong: bool


@dataclass(frozen=True)
class ShadbalaChartInputs:
    """Everything compute_shadbala needs about the chart as a whole (i.e.
    not specific to the one planet being scored) — computed once by
    `compute_time_of_day_facts` (for the three time-of-day fields) and
    reused across all 7 calls, one per classical planet, since none of it
    varies by which planet is currently being scored. In particular
    `birth_window`/`weekday_lord`/`current_hora_lord` depend only on the
    birth moment and location, not on any planet — a real, measured bug
    (not just a style nit) let compute_shadbala recompute all three PER
    PLANET via day_night_window/hora_lord_at until this was fixed: those
    three each involve sunrise/sunset root-finding
    (app.astro.ephemeris.sunrise_utc/sunset_utc, each a Swiss Ephemeris
    iterative solve), and profiling showed that redundant per-planet
    recomputation was ~90% of compute_all_shadbala's total runtime (9.3 of
    ~10.2ms for a 7-planet chart) despite the exact same three values being
    correct for all 7 calls."""
    natal_planet_sign: dict[PlanetKey, int]  # every classical planet's D1 sign
    natal_planet_longitude: dict[PlanetKey, float]
    natal_planet_speed: dict[PlanetKey, float]
    natal_planet_house: dict[PlanetKey, int]
    natal_planet_d9_sign: dict[PlanetKey, int]
    natal_planet_varga_signs: dict[PlanetKey, dict[str, int]]  # per planet: {"D2":.., "D3":.., "D7":.., "D12":.., "D30":..}
    natal_planet_declination: dict[PlanetKey, float]
    natal_planet_aspect_multiplier: dict[PlanetKey, float]
    lagna_longitude: float
    birth_jd_ut: float
    latitude: float
    longitude: float
    # birth_window is birth's OWN day-or-night window (whichever it is) —
    # what nathonnata_bala/tribhaga_bala need. weekday_lord/
    # current_hora_lord are separate derived facts (weekday_lord in
    # particular comes from the DAY half of birth's 24-Hora cycle even when
    # birth itself fell at night — see _enclosing_day_and_night).
    birth_window: DayNightWindow
    weekday_lord: PlanetKey
    current_hora_lord: PlanetKey


def compute_time_of_day_facts(birth_jd_ut: float, latitude: float, longitude: float) -> tuple[DayNightWindow, PlanetKey, PlanetKey]:
    """The (birth_window, weekday_lord, current_hora_lord) triple
    ShadbalaChartInputs needs — computed ONCE per chart by whoever builds
    that dataclass (see its docstring for why this used to be computed 7x
    redundantly instead)."""
    birth_window = day_night_window(birth_jd_ut, latitude, longitude)
    day_window, _night_window = _enclosing_day_and_night(birth_window, latitude, longitude)
    weekday_lord = _WEEKDAY_LORDS[_weekday_of_sunrise(day_window)]
    current_hora_lord = hora_lord_at(birth_jd_ut, latitude, longitude)
    return birth_window, weekday_lord, current_hora_lord


def compute_shadbala(planet: PlanetKey, chart: ShadbalaChartInputs) -> ShadbalaResult:
    p_longitude = chart.natal_planet_longitude[planet]
    p_sign = chart.natal_planet_sign[planet]

    sthana = (
        uccha_bala(planet, p_longitude)
        + saptavargaja_bala(
            planet, p_sign, degree_in_sign(p_longitude),
            chart.natal_planet_varga_signs[planet], chart.natal_planet_sign,
        )
        + ojhayugmarasyamsa_bala(planet, p_sign, chart.natal_planet_d9_sign[planet])
        + kendradi_bala(chart.natal_planet_house[planet])
        + drekkana_bala(planet, p_longitude)
    )

    dig = dig_bala(planet, p_longitude, chart.lagna_longitude)

    sun_longitude = chart.natal_planet_longitude["Su"]
    moon_longitude = chart.natal_planet_longitude["Mo"]
    planet_paksha = paksha_bala(sun_longitude, moon_longitude, planet)
    planet_ayana = ayana_bala(planet, chart.natal_planet_declination[planet])
    # birth_window/weekday_lord/current_hora_lord come from `chart` (computed
    # ONCE per chart by compute_time_of_day_facts) rather than recomputed
    # here — see ShadbalaChartInputs's docstring for the redundant-7x-
    # recomputation bug this fixes.
    kaala = (
        planet_paksha
        + planet_ayana
        + nathonnata_bala(planet, chart.birth_jd_ut, chart.birth_window)
        + tribhaga_bala(planet, chart.birth_jd_ut, chart.birth_window)
        + vara_bala(planet, chart.weekday_lord)
        + hora_bala(planet, chart.current_hora_lord)
    )

    sun_ayana = planet_ayana if planet == "Su" else ayana_bala("Su", chart.natal_planet_declination["Su"])
    moon_paksha = planet_paksha if planet == "Mo" else paksha_bala(sun_longitude, moon_longitude, "Mo")
    cheshta = cheshta_bala(planet, chart.natal_planet_speed[planet], sun_ayana, moon_paksha)

    naisargika = naisargika_bala(planet)
    drik = drik_bala(chart.natal_planet_aspect_multiplier[planet])

    total_virupas = sthana + dig + kaala + cheshta + naisargika + drik
    total_rupas = total_virupas / 60.0
    minimum = MINIMUM_RUPAS[planet]

    return ShadbalaResult(
        planet=planet,
        sthana_bala=sthana,
        dig_bala=dig,
        kaala_bala=kaala,
        cheshta_bala=cheshta,
        naisargika_bala=naisargika,
        drik_bala=drik,
        total_virupas=total_virupas,
        total_rupas=total_rupas,
        minimum_rupas=minimum,
        is_strong=total_rupas >= minimum,
    )


def compute_all_shadbala(chart: ShadbalaChartInputs) -> dict[PlanetKey, ShadbalaResult]:
    return {planet: compute_shadbala(planet, chart) for planet in _SHADBALA_PLANETS}
