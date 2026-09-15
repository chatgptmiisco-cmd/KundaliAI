"""Ashtakavarga (Bhinnashtakavarga): the classical point-scoring system used
to judge whether a planet's TRANSIT through a given sign is actually
favorable, rather than treating "any transit through the classically right
house" as an unconditional good sign — a real astrologer weighs a transit's
own Ashtakavarga bindu count (0-8) at that sign at least as heavily as the
house's general significance.

Every one of the 7 classical planets has its own Bhinnashtakavarga (BAV): 12
zodiac signs, each scored 0-8 by summing a fixed classical "does this sign
earn a point" table from 8 contributors — the 7 classical planets plus the
Lagna, each counted from THEIR OWN natal sign, not the target planet's.
E.g. Saturn's BAV asks "which signs, counted as the Nth sign from the SUN's
own natal sign, earn Saturn a point" — not from Saturn's own sign. The
result is a per-chart, per-target-planet table that doesn't change over
time; what changes with a transit is only which sign is being looked up in
it (the transiting planet's CURRENT sign).

Rahu/Ketu deliberately have no Ashtakavarga here — same "not part of the
core Parashari system" convention as excluding them from dignity
(app.astro.constants.EXALTATION_SIGN) and special aspects
(app.astro.constants.SPECIAL_ASPECT_HOUSES).

The house-lists below are the fixed classical BAV tables (Brihat Parashara
Hora Shastra). A transcription error across the 56 rows here (7 planets x 8
contributors) would be silent and easy to introduce, so every row's point
count AND the grand total are checked against the universally published,
chart-independent totals — Sun 48, Moon 49, Mars 39, Mercury 54, Jupiter 56,
Venus 52, Saturn 39, summing to a fixed 337 — by
test_ashtakavarga_row_and_grand_totals_match_the_published_constants.
"""
from typing import Literal

from app.astro.constants import PlanetKey

AshtakavargaPlanet = Literal["Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa"]
_Contributor = Literal["Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Lagna"]

ASHTAKAVARGA_PLANETS: tuple[AshtakavargaPlanet, ...] = ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa")
_CONTRIBUTORS: tuple[_Contributor, ...] = ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Lagna")

# BAV_TABLES[target_planet][contributor] = which "Nth sign from the
# contributor's own natal sign" (1-12) earns `target_planet` a bindu.
BAV_TABLES: dict[AshtakavargaPlanet, dict[_Contributor, tuple[int, ...]]] = {
    "Su": {
        "Su": (1, 2, 4, 7, 8, 9, 10, 11), "Mo": (3, 6, 10, 11), "Ma": (1, 2, 4, 7, 8, 9, 10, 11),
        "Me": (3, 5, 6, 9, 10, 11, 12), "Ju": (5, 6, 9, 11), "Ve": (6, 7, 12),
        "Sa": (1, 2, 4, 7, 8, 9, 10, 11), "Lagna": (3, 4, 6, 10, 11, 12),
    },
    "Mo": {
        "Su": (3, 6, 7, 8, 10, 11), "Mo": (1, 3, 6, 7, 10, 11), "Ma": (2, 3, 5, 6, 9, 10, 11),
        "Me": (1, 3, 4, 5, 7, 8, 10, 11), "Ju": (1, 4, 7, 8, 10, 11, 12), "Ve": (3, 4, 5, 7, 9, 10, 11),
        "Sa": (3, 5, 6, 11), "Lagna": (3, 6, 10, 11),
    },
    "Ma": {
        "Su": (3, 5, 6, 10, 11), "Mo": (3, 6, 11), "Ma": (1, 2, 4, 7, 8, 10, 11),
        "Me": (3, 5, 6, 11), "Ju": (6, 10, 11, 12), "Ve": (6, 8, 11, 12),
        "Sa": (1, 4, 7, 8, 9, 10, 11), "Lagna": (1, 3, 6, 10, 11),
    },
    "Me": {
        "Su": (5, 6, 9, 11, 12), "Mo": (2, 4, 6, 8, 10, 11), "Ma": (1, 2, 4, 7, 8, 9, 10, 11),
        "Me": (1, 3, 5, 6, 9, 10, 11, 12), "Ju": (6, 8, 11, 12), "Ve": (1, 2, 3, 4, 5, 8, 9, 11),
        "Sa": (1, 2, 4, 7, 8, 9, 10, 11), "Lagna": (1, 2, 4, 6, 8, 10, 11),
    },
    "Ju": {
        "Su": (1, 2, 3, 4, 7, 8, 9, 10, 11), "Mo": (2, 5, 7, 9, 11), "Ma": (1, 2, 4, 7, 8, 10, 11),
        "Me": (1, 2, 4, 5, 6, 9, 10, 11), "Ju": (1, 2, 3, 4, 7, 8, 10, 11), "Ve": (2, 5, 6, 9, 10, 11),
        "Sa": (3, 5, 6, 12), "Lagna": (1, 2, 4, 5, 6, 7, 9, 10, 11),
    },
    "Ve": {
        "Su": (8, 11, 12), "Mo": (1, 2, 3, 4, 5, 8, 9, 11, 12), "Ma": (3, 5, 6, 9, 11, 12),
        "Me": (3, 5, 6, 9, 11), "Ju": (5, 8, 9, 10, 11), "Ve": (1, 2, 3, 4, 5, 8, 9, 10, 11),
        "Sa": (3, 4, 5, 8, 9, 10, 11), "Lagna": (1, 2, 3, 4, 5, 8, 9, 11),
    },
    "Sa": {
        "Su": (1, 2, 4, 7, 8, 10, 11), "Mo": (3, 6, 11), "Ma": (3, 5, 6, 10, 11, 12),
        "Me": (6, 8, 9, 10, 11, 12), "Ju": (5, 6, 11, 12), "Ve": (6, 11, 12),
        "Sa": (3, 5, 6, 11), "Lagna": (1, 3, 4, 6, 10, 11),
    },
}

# Fixed classical totals (Brihat Parashara Hora Shastra) — every chart's
# Bhinnashtakavarga for a given planet sums to exactly this across its 12
# signs, regardless of the actual birth data, since BAV_TABLES above is a
# fixed lookup rule, not something that varies by chart. Consumed only by
# the self-check test, not by compute_bav — see the module docstring.
BAV_TOTAL_BINDUS: dict[AshtakavargaPlanet, int] = {
    "Su": 48, "Mo": 49, "Ma": 39, "Me": 54, "Ju": 56, "Ve": 52, "Sa": 39,
}


def compute_bav(
    target_planet: AshtakavargaPlanet,
    natal_planet_sign_index: dict[PlanetKey, int],
    natal_lagna_sign_index: int,
) -> dict[int, int]:
    """Bhinnashtakavarga for `target_planet`: bindu count (0-8) per zodiac
    sign index (0-11), computed once from natal data — the transiting
    planet's CURRENT sign is looked up against this fixed table by the
    caller (see app.astro.event_window_scanner / marriage_timing /
    life_event_timing's transit-corroboration checks), not recomputed per
    transit date."""
    table = BAV_TABLES[target_planet]
    contributor_signs: dict[_Contributor, int] = {
        contributor: natal_planet_sign_index[contributor] for contributor in ASHTAKAVARGA_PLANETS
    }
    contributor_signs["Lagna"] = natal_lagna_sign_index

    bindus: dict[int, int] = {sign: 0 for sign in range(12)}
    for contributor, contributor_sign in contributor_signs.items():
        earning_house_numbers = table[contributor]
        for sign in range(12):
            # The house-number (1-12) that `sign` represents counting from
            # the contributor's own sign — e.g. the sign right after the
            # contributor's own is house-number 2 "from" it.
            house_number_from_contributor = ((sign - contributor_sign) % 12) + 1
            if house_number_from_contributor in earning_house_numbers:
                bindus[sign] += 1
    return bindus


# Classical rule-of-thumb bands for reading a single BAV sign's bindu count
# (0-8): 5-8 is a strong, favorable transit through that sign; 4 is
# average/unremarkable; 3 or fewer is weak. Used to scale (not replace) the
# Prediction Engine's existing transit-corroboration bonus — see
# prediction_service._TRANSIT_CORROBORATION_BONUS — so a transit through a
# classically "right" house that ALSO has strong Ashtakavarga support counts
# for more than one with weak support, instead of every corroborating
# transit counting identically regardless of its own bindu strength.
_ASHTAKAVARGA_STRENGTH_MULTIPLIER: dict[int, float] = {
    0: 0.5, 1: 0.5, 2: 0.5,
    3: 0.75,
    4: 1.0,
    5: 1.25, 6: 1.25,
    7: 1.5, 8: 1.5,
}


def ashtakavarga_strength_multiplier(bindus: int) -> float:
    return _ASHTAKAVARGA_STRENGTH_MULTIPLIER[bindus]
