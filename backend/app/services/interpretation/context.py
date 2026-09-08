"""Builds the plain-dict astrology context handed to interpreters.

Kept as one shared shape/builder so the Claude implementation and the
template fallback are always describing the same facts.
"""
from typing import Any, Literal

from app.astro.charts import ChartResult
from app.astro.constants import (
    PLANET_NAMES_EN,
    PLANET_NAMES_HI,
    SIGN_NAMES_EN,
    SIGN_NAMES_HI,
    PlanetKey,
)
from app.astro.dasha import Antardasha, Mahadasha, SubPeriod
from app.astro.transits import TransitSnapshot

Language = Literal["en", "hi"]


def _planet_name(planet: PlanetKey, language: Language) -> str:
    return (PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN)[planet]


def _sign_name(sign_index: int, language: Language) -> str:
    return (SIGN_NAMES_HI if language == "hi" else SIGN_NAMES_EN)[sign_index]


def build_natal_context(chart: ChartResult, language: Language) -> dict[str, Any]:
    planets = []
    for planet, sign in chart.planet_sign_index.items():
        planets.append(
            {
                "planet": _planet_name(planet, language),
                "sign": _sign_name(sign, language),
                "house": chart.planet_house[planet],
                "retrograde": chart.planet_retrograde[planet],
            }
        )
    return {
        "lagna_sign": _sign_name(chart.lagna_sign_index, language),
        "planets": planets,
    }


def build_dasha_context(
    mahadasha: Mahadasha,
    antardasha: Antardasha,
    pratyantardasha: SubPeriod | None,
    language: Language,
) -> dict[str, Any]:
    return {
        "mahadasha_lord": _planet_name(mahadasha.lord, language),
        "mahadasha_lord_key": mahadasha.lord,
        "antardasha_lord": _planet_name(antardasha.lord, language),
        "antardasha_lord_key": antardasha.lord,
        "pratyantardasha_lord": _planet_name(pratyantardasha.lord, language) if pratyantardasha else None,
        "pratyantardasha_lord_key": pratyantardasha.lord if pratyantardasha else None,
    }


def build_transit_context(snapshot: TransitSnapshot, language: Language) -> dict[str, Any]:
    highlights = []
    for planet, house in snapshot.planet_house_from_moon.items():
        highlights.append(
            {
                "planet": _planet_name(planet, language),
                "house_from_moon": house,
                "house_from_lagna": snapshot.planet_house_from_lagna[planet],
                "retrograde": snapshot.planet_retrograde[planet],
            }
        )
    return {"transit_highlights": highlights}
