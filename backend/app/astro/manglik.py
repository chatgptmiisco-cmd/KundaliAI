"""Manglik (Mangal) dosha: a well-known, simple placement rule — Mars in
houses 1, 2, 4, 7, 8 or 12 counted from the Lagna. Some traditions also check
from the Moon; both are computed and returned so the interpretation layer
can present either or both.

Takes plain sign/house indices rather than a ChartResult so callers can pass
in whatever they already have on hand (e.g. an already-cached D1 chart's
placements) without recomputing anything.
"""
from dataclasses import dataclass

from app.astro.charts import house_number

MANGLIK_HOUSES = {1, 2, 4, 7, 8, 12}
_ARIES, _SCORPIO = 0, 7  # Mars's own signs


@dataclass(frozen=True)
class ManglikFacts:
    is_manglik: bool
    mars_house_from_lagna: int
    mars_house_from_moon: int
    mars_in_own_sign: bool


def compute_manglik_facts(mars_sign_index: int, mars_house_from_lagna: int, moon_sign_index: int) -> ManglikFacts:
    mars_house_from_moon = house_number(mars_sign_index, moon_sign_index)
    return ManglikFacts(
        is_manglik=mars_house_from_lagna in MANGLIK_HOUSES,
        mars_house_from_lagna=mars_house_from_lagna,
        mars_house_from_moon=mars_house_from_moon,
        mars_in_own_sign=mars_sign_index in (_ARIES, _SCORPIO),
    )
