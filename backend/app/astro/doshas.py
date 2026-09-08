"""Dosha catalog beyond Manglik (see app.astro.manglik for that one). Each
function here is the same "plain sign/house indices in, plain dataclass out"
shape used across app.astro — no LLM, just classical placement rules.

This is a deliberately small starter catalog: Kaal Sarp, Sade Sati, and
Kemadruma. Grahan Dosha and Pitru Dosha are classically murkier (they depend
on eclipse-adjacent nuance and ancestral-affliction readings that vary more
across traditions) and are left out rather than shipped as a guess — a clear
follow-up, not a silent gap.

Two of the three below use a documented simplification, same convention as
app.astro.guna_milan:
  - Kaal Sarp: the classical rule is "every planet falls between Rahu and
    Ketu going one direction, none crossing" — implemented here as "every
    classical planet's house-from-Rahu falls entirely within 2-6 or entirely
    within 8-12" (Ketu always sits in house 7 from Rahu), which is exactly
    that rule expressed in whole-sign house terms.
  - Kemadruma: this module treats the dosha as present only when BOTH the
    base condition (no planet in the 2nd/12th from Moon) AND the classical
    cancellation check (no planet in a Kendra from Moon) fail to cancel it —
    i.e. it folds the bhanga (cancellation) rule into the presence check
    rather than reporting it separately.
"""
from dataclasses import dataclass
from typing import Literal

from app.astro.charts import house_number
from app.astro.constants import PlanetKey

CLASSICAL_PLANETS: tuple[PlanetKey, ...] = ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa")

SadeSatiPhase = Literal["rising", "peak", "setting"]
_KENDRA_FROM_MOON = {1, 4, 7, 10}
_ADJACENT_FROM_MOON = {2, 12}


@dataclass(frozen=True)
class KaalSarpFacts:
    is_present: bool
    rahu_house: int  # from Lagna
    ketu_house: int  # from Lagna


def compute_kaal_sarp_dosha(
    lagna_sign_index: int,
    rahu_sign_index: int,
    ketu_sign_index: int,
    planet_sign_index: dict[PlanetKey, int],
) -> KaalSarpFacts:
    houses_from_rahu = [
        house_number(planet_sign_index[p], rahu_sign_index)
        for p in CLASSICAL_PLANETS
        if p in planet_sign_index
    ]
    one_side = bool(houses_from_rahu) and all(2 <= h <= 6 for h in houses_from_rahu)
    other_side = bool(houses_from_rahu) and all(8 <= h <= 12 for h in houses_from_rahu)
    return KaalSarpFacts(
        is_present=one_side or other_side,
        rahu_house=house_number(rahu_sign_index, lagna_sign_index),
        ketu_house=house_number(ketu_sign_index, lagna_sign_index),
    )


@dataclass(frozen=True)
class SadeSatiFacts:
    is_active: bool
    phase: SadeSatiPhase | None
    house_from_moon: int


def compute_sade_sati(natal_moon_sign_index: int, transiting_saturn_sign_index: int) -> SadeSatiFacts:
    house = house_number(transiting_saturn_sign_index, natal_moon_sign_index)
    phase_by_house: dict[int, SadeSatiPhase] = {12: "rising", 1: "peak", 2: "setting"}
    phase = phase_by_house.get(house)
    return SadeSatiFacts(is_active=phase is not None, phase=phase, house_from_moon=house)


@dataclass(frozen=True)
class KemadrumaFacts:
    is_present: bool


def compute_kemadruma_dosha(planet_house_from_moon: dict[PlanetKey, int]) -> KemadrumaFacts:
    """`planet_house_from_moon` should exclude the Moon itself."""
    houses = set(planet_house_from_moon.values())
    no_adjacent_support = not (houses & _ADJACENT_FROM_MOON)
    no_kendra_cancellation = not (houses & _KENDRA_FROM_MOON)
    return KemadrumaFacts(is_present=no_adjacent_support and no_kendra_cancellation)
