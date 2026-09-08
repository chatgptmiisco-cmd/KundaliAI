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
    OWN_SIGNS,
    SIGN_MODALITY,
    PlanetKey,
    SIGN_LORDS,
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
