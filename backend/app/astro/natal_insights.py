"""Rule-based natal chart insights: house-lord placements and planetary
dignity (exalted/debilitated/own-sign/neutral), derived from an already
computed D1 chart.

This is the deterministic reasoning a Vedic astrologer applies by hand —
"the 10th lord sits in the 6th house", "Saturn is debilitated" — and is what
lets app.services.interpretation.templates describe a genuinely different
chart per birth instead of only varying by the current Mahadasha lord (9
possibilities) and Lagna sign (12 possibilities). No LLM call involved.

Takes plain sign/house dicts rather than a ChartResponse so callers can pass
in whatever they already have on hand (mirrors app.astro.manglik's style).
"""
from dataclasses import dataclass
from typing import Literal

from app.astro.constants import (
    DEBILITATION_SIGN,
    EXALTATION_SIGN,
    NATURAL_BENEFICS,
    NATURAL_MALEFICS,
    OWN_SIGNS,
    SIGN_MODALITY,
    PlanetKey,
    SIGN_LORDS,
    aspected_houses_from,
)

Dignity = Literal["exalted", "debilitated", "own_sign", "neutral"]
BlindSpotReason = Literal["dusthana_placement", "debilitated", "combust", "none"]
DecisionStyle = Literal[
    "fast_and_decisive", "steady_and_persistent", "adaptive_and_scattered", "impulsive_and_reactive"
]

# Rahu/Ketu excluded — see the note on EXALTATION_SIGN in app.astro.constants.
_CLASSICAL_PLANETS: tuple[PlanetKey, ...] = ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa")

_DUSTHANA_HOUSES = {6, 8, 12}

# Classical combustion (Asta) orbs in degrees from the Sun, per planet — the
# Moon is excluded from most texts' combustion list but commonly included
# for a "too close to the Sun to see" reading; retrograde-tightened orbs are
# a documented simplification not applied here (single orb per planet).
_COMBUSTION_ORB_DEG: dict[PlanetKey, float] = {
    "Mo": 12.0, "Ma": 17.0, "Me": 14.0, "Ju": 11.0, "Ve": 10.0, "Sa": 15.0,
}

_MODALITY_STYLE: dict[int, DecisionStyle] = {
    0: "fast_and_decisive", 1: "steady_and_persistent", 2: "adaptive_and_scattered",
}


def sign_lord(sign_idx: int) -> PlanetKey:
    return SIGN_LORDS[sign_idx]


def house_sign(house: int, lagna_sign_index: int) -> int:
    """Sign index occupying whole-sign `house` (1-12), given the Lagna's sign."""
    return (lagna_sign_index + house - 1) % 12


def house_lord(house: int, lagna_sign_index: int) -> PlanetKey:
    return sign_lord(house_sign(house, lagna_sign_index))


def planet_dignity(planet: PlanetKey, sign_idx: int) -> Dignity:
    if EXALTATION_SIGN.get(planet) == sign_idx:
        return "exalted"
    if DEBILITATION_SIGN.get(planet) == sign_idx:
        return "debilitated"
    if sign_idx in OWN_SIGNS.get(planet, []):
        return "own_sign"
    return "neutral"


def is_combust(planet: PlanetKey, planet_longitude: float, sun_longitude: float) -> bool:
    orb = _COMBUSTION_ORB_DEG.get(planet)
    if orb is None:  # Sun itself, and Rahu/Ketu, are never "combust"
        return False
    separation = abs((planet_longitude - sun_longitude + 180) % 360 - 180)
    return separation <= orb


# Multiplies a Prediction-Engine dasha-window rule's classical weight by how
# strong that significator actually is in THIS person's chart — a real
# astrologer reads "Venus's Antardasha" very differently for an exalted,
# unafflicted Venus than for a debilitated, combust, dusthana-placed one,
# rather than treating every classical "X's period" rule as equally strong
# regardless of the birth chart. Dignity is the dominant factor; dusthana
# (6/8/12) placement and combustion are independent afflictions that stack
# on top of it, same as a real reading. Clamped to [0.3, 1.5] so this stays a
# tilt on the classical rule weight (which already encodes "how important is
# this signal") rather than a replacement for it or a way to zero one out.
_DIGNITY_STRENGTH_MULTIPLIER: dict[Dignity, float] = {
    "exalted": 1.5, "own_sign": 1.25, "neutral": 1.0, "debilitated": 0.5,
}
_DUSTHANA_STRENGTH_MULTIPLIER = 0.75
_COMBUST_STRENGTH_MULTIPLIER = 0.85
_MIN_STRENGTH_MULTIPLIER, _MAX_STRENGTH_MULTIPLIER = 0.3, 1.5

# A benefic's classical drishti (aspect) on a planet is real support; a
# malefic's is a real affliction — even for a planet that's otherwise
# perfectly well-placed by sign. A CONJUNCTION (sharing the same house) is
# the closer, stronger version of the same influence (Yuti, not drishti),
# so it moves the needle further than a distant aspect. Both stack when
# multiple planets are involved (three malefics aspecting the same planet is
# genuinely worse than one), same convention as dusthana/combustion above.
_BENEFIC_ASPECT_MULTIPLIER = 1.1
_MALEFIC_ASPECT_MULTIPLIER = 0.9
_BENEFIC_CONJUNCTION_MULTIPLIER = 1.15
_MALEFIC_CONJUNCTION_MULTIPLIER = 0.85


def significator_strength(
    dignity: Dignity,
    house: int,
    combust: bool,
    aspect_multiplier: float = 1.0,
    vargottama_multiplier: float = 1.0,
    shadbala_multiplier: float = 1.0,
) -> float:
    multiplier = _DIGNITY_STRENGTH_MULTIPLIER[dignity]
    if house in _DUSTHANA_HOUSES:
        multiplier *= _DUSTHANA_STRENGTH_MULTIPLIER
    if combust:
        multiplier *= _COMBUST_STRENGTH_MULTIPLIER
    multiplier *= aspect_multiplier
    multiplier *= vargottama_multiplier
    multiplier *= shadbala_multiplier
    return max(_MIN_STRENGTH_MULTIPLIER, min(_MAX_STRENGTH_MULTIPLIER, multiplier))


# Vargottama: a planet occupying the SAME sign in D1 (Rasi) and D9 (Navamsa)
# is classically treated as unusually stable/reliable — its D1 placement is
# "confirmed" by the finer-grained Navamsa instead of shifting elsewhere, a
# real and simple (one sign match, no degree nuance) classical strength
# booster distinct from dignity, aspect, or Shadbala.
_VARGOTTAMA_MULTIPLIER = 1.15


def vargottama_multiplier(d1_sign: int, d9_sign: int) -> float:
    return _VARGOTTAMA_MULTIPLIER if d1_sign == d9_sign else 1.0


# Rescales Shadbala's continuous Rupas-vs-minimum-threshold ratio (see
# app.astro.shadbala) into the same multiplicative-tilt shape as every other
# factor here — clamped to +/-30% so this genuinely comprehensive six-limb
# strength measure still only TILTS the classical rule weight rather than
# overriding it outright, same convention as every other factor above.
_SHADBALA_MIN_MULTIPLIER, _SHADBALA_MAX_MULTIPLIER = 0.7, 1.3


def shadbala_strength_multiplier(total_rupas: float, minimum_rupas: float) -> float:
    ratio = total_rupas / minimum_rupas
    return max(_SHADBALA_MIN_MULTIPLIER, min(_SHADBALA_MAX_MULTIPLIER, ratio))


def aspect_and_conjunction_multiplier(
    planet: PlanetKey, house: int, planet_house: dict[PlanetKey, int]
) -> float:
    """Combined benefic-support/malefic-affliction multiplier for `planet`
    (sitting in `house`) from every OTHER planet in `planet_house` that
    aspects or conjoins it — see app.astro.constants.aspected_houses_from
    for the underlying Parashari drishti rule and NATURAL_BENEFICS/
    NATURAL_MALEFICS for the benefic/malefic classification."""
    multiplier = 1.0
    for other, other_house in planet_house.items():
        if other == planet:
            continue
        if other_house == house:
            if other in NATURAL_BENEFICS:
                multiplier *= _BENEFIC_CONJUNCTION_MULTIPLIER
            elif other in NATURAL_MALEFICS:
                multiplier *= _MALEFIC_CONJUNCTION_MULTIPLIER
        elif house in aspected_houses_from(other, other_house):
            if other in NATURAL_BENEFICS:
                multiplier *= _BENEFIC_ASPECT_MULTIPLIER
            elif other in NATURAL_MALEFICS:
                multiplier *= _MALEFIC_ASPECT_MULTIPLIER
    return multiplier


def significator_strength_multipliers(
    planet_sign_index: dict[PlanetKey, int],
    planet_house: dict[PlanetKey, int],
    planet_longitude: dict[PlanetKey, float] | None = None,
    planet_d9_sign_index: dict[PlanetKey, int] | None = None,
    shadbala_results: dict[PlanetKey, object] | None = None,
) -> dict[PlanetKey, float]:
    """One `significator_strength` multiplier per planet present in both
    `planet_sign_index` and `planet_house` — the per-chart input the
    Prediction Engine's window scanner (app.astro.event_window_scanner) needs
    to scale its classical rule weights by real chart strength. Combustion is
    only checked when `planet_longitude` is supplied (mirrors
    compute_natal_insights's same optional parameter) and includes the Sun's
    own longitude under the "Su" key. Aspect/conjunction affliction-or-
    support is computed from every planet present in `planet_house`,
    regardless of whether it also appears in `planet_sign_index` — a partial
    `planet_sign_index` (e.g. only classical planets) shouldn't silently
    drop Rahu/Ketu's very real conjunctions/aspects on someone else.

    `planet_d9_sign_index` (Navamsa sign per planet) enables the Vargottama
    factor; `shadbala_results` (app.astro.shadbala.ShadbalaResult per planet,
    or anything with `.total_rupas`/`.minimum_rupas`) enables the Shadbala
    factor. Both are optional and default to no adjustment (1.0) when
    omitted, so existing callers that don't have D9/Shadbala data on hand
    are unaffected."""
    sun_longitude = (planet_longitude or {}).get("Su")
    multipliers: dict[PlanetKey, float] = {}
    for planet, sign_idx in planet_sign_index.items():
        house = planet_house.get(planet)
        if house is None:
            continue
        combust = (
            sun_longitude is not None
            and planet_longitude is not None
            and planet in planet_longitude
            and is_combust(planet, planet_longitude[planet], sun_longitude)
        )
        aspect_multiplier = aspect_and_conjunction_multiplier(planet, house, planet_house)
        varga_multiplier = (
            vargottama_multiplier(sign_idx, planet_d9_sign_index[planet])
            if planet_d9_sign_index is not None and planet in planet_d9_sign_index
            else 1.0
        )
        shadbala_multiplier = (
            shadbala_strength_multiplier(shadbala_results[planet].total_rupas, shadbala_results[planet].minimum_rupas)
            if shadbala_results is not None and planet in shadbala_results
            else 1.0
        )
        multipliers[planet] = significator_strength(
            planet_dignity(planet, sign_idx), house, combust, aspect_multiplier,
            varga_multiplier, shadbala_multiplier,
        )
    return multipliers


@dataclass(frozen=True)
class NatalInsights:
    lagna_lord: PlanetKey
    lagna_lord_house: int
    tenth_lord: PlanetKey
    tenth_lord_house: int
    seventh_lord: PlanetKey
    seventh_lord_house: int
    sixth_lord: PlanetKey
    sixth_lord_house: int
    planet_dignity: dict[PlanetKey, Dignity]
    # First exalted planet found (else first own-sign planet found), and
    # first debilitated planet found — a lightweight, explainable stand-in
    # for full Shadbala strength scoring.
    strongest_planet: PlanetKey | None
    weakest_planet: PlanetKey | None
    # All 12 house lords and the house each currently occupies — generalizes
    # the 4 named lords above (lagna/6th/7th/10th) to every house, which is
    # what a "9th-house life-growth task" or "8th/12th blind spot" reading
    # needs and the original 4-house version couldn't provide.
    house_lords: dict[int, PlanetKey]
    house_lord_houses: dict[int, int]
    # Populated only when planet_longitude is supplied to compute_natal_insights
    # (combustion needs real longitudes, not just sign/house placement).
    combust_planets: frozenset[PlanetKey]
    blind_spot_planet: PlanetKey
    blind_spot_reason: BlindSpotReason
    stress_house: int  # whichever of 6/8/12 is most afflicted
    stress_planet: PlanetKey
    decision_style: DecisionStyle


def compute_natal_insights(
    lagna_sign_index: int,
    planet_sign_index: dict[PlanetKey, int],
    planet_house: dict[PlanetKey, int],
    planet_longitude: dict[PlanetKey, float] | None = None,
) -> NatalInsights:
    def lord_and_house(house: int) -> tuple[PlanetKey, int]:
        lord = house_lord(house, lagna_sign_index)
        return lord, planet_house[lord]

    lagna_lord, lagna_lord_house = lord_and_house(1)
    tenth_lord, tenth_lord_house = lord_and_house(10)
    seventh_lord, seventh_lord_house = lord_and_house(7)
    sixth_lord, sixth_lord_house = lord_and_house(6)

    dignity = {
        p: planet_dignity(p, planet_sign_index[p]) for p in _CLASSICAL_PLANETS if p in planet_sign_index
    }

    strongest = next((p for p in _CLASSICAL_PLANETS if dignity.get(p) == "exalted"), None)
    if strongest is None:
        strongest = next((p for p in _CLASSICAL_PLANETS if dignity.get(p) == "own_sign"), None)
    weakest = next((p for p in _CLASSICAL_PLANETS if dignity.get(p) == "debilitated"), None)

    house_lords = {house: house_lord(house, lagna_sign_index) for house in range(1, 13)}
    house_lord_houses = {house: planet_house[lord] for house, lord in house_lords.items()}

    combust_planets: frozenset[PlanetKey] = frozenset()
    if planet_longitude and "Su" in planet_longitude:
        sun_longitude = planet_longitude["Su"]
        combust_planets = frozenset(
            p for p in _CLASSICAL_PLANETS
            if p != "Su" and p in planet_longitude and is_combust(p, planet_longitude[p], sun_longitude)
        )

    # Blind spot: the Lagna lord itself if it's genuinely afflicted (sitting
    # in a dusthana, debilitated, or combust); otherwise fall back to the
    # chart's weakest placement, if any — a chart with neither has no real
    # blind spot to report.
    if lagna_lord_house in _DUSTHANA_HOUSES:
        blind_spot_planet, blind_spot_reason = lagna_lord, "dusthana_placement"
    elif dignity.get(lagna_lord) == "debilitated":
        blind_spot_planet, blind_spot_reason = lagna_lord, "debilitated"
    elif lagna_lord in combust_planets:
        blind_spot_planet, blind_spot_reason = lagna_lord, "combust"
    elif weakest is not None:
        blind_spot_planet, blind_spot_reason = weakest, "debilitated"
    else:
        blind_spot_planet, blind_spot_reason = lagna_lord, "none"

    # Stress pattern: among the three dusthana (6th/8th/12th) lords, whichever
    # is most afflicted (debilitated outweighs combust); ties favour the
    # lower house number.
    def _severity(planet: PlanetKey) -> int:
        score = 0
        if dignity.get(planet) == "debilitated":
            score += 2
        if planet in combust_planets:
            score += 1
        return score

    stress_house = max((6, 8, 12), key=lambda h: (_severity(house_lords[h]), -h))
    stress_planet = house_lords[stress_house]

    mercury_dignity = dignity.get("Me", "neutral")
    style = _MODALITY_STYLE[SIGN_MODALITY[lagna_sign_index]]
    if mercury_dignity == "debilitated" and style == "fast_and_decisive":
        style = "impulsive_and_reactive"

    return NatalInsights(
        lagna_lord=lagna_lord,
        lagna_lord_house=lagna_lord_house,
        tenth_lord=tenth_lord,
        tenth_lord_house=tenth_lord_house,
        seventh_lord=seventh_lord,
        seventh_lord_house=seventh_lord_house,
        sixth_lord=sixth_lord,
        sixth_lord_house=sixth_lord_house,
        planet_dignity=dignity,
        strongest_planet=strongest,
        weakest_planet=weakest,
        house_lords=house_lords,
        house_lord_houses=house_lord_houses,
        combust_planets=combust_planets,
        blind_spot_planet=blind_spot_planet,
        blind_spot_reason=blind_spot_reason,
        stress_house=stress_house,
        stress_planet=stress_planet,
        decision_style=style,
    )
