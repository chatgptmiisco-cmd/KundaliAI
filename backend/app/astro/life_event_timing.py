"""Life-event timing prediction, generalized across four classically
well-established real-life questions: career/job change, financial growth,
children, and foreign travel/relocation. Each has a well-defined house +
karaka (significator) set, run through the same generic window scanner
(app.astro.event_window_scanner) that app.astro.marriage_timing already
uses — this module is the same pattern applied to a parametrized event type
instead of duplicated per event.

`marriage_timing.py` is deliberately left untouched (already shipped,
tested, wired into chat) rather than folded into this generic module — not
worth the risk of refactoring working code into a shared abstraction.

Produces ranked *probable favorable windows*, never a fabricated exact
date — same honesty rule as marriage timing.
"""
from datetime import datetime
from typing import Literal

from app.astro.constants import PlanetKey
from app.astro.dasha import Mahadasha
from app.astro.event_karakas import CATEGORY_KARAKAS, karaka_specificity_multiplier
from app.astro.event_window_scanner import ScoredWindow, WindowRule, scan_dasha_windows
from app.astro.transit_corroboration import TransitCheck, check_transits

EventType = Literal[
    "career", "wealth", "children", "foreign_travel",
    "career_promotion", "business_partnership", "business_expansion",
    "property",
]

# The house each event classically activates. career_promotion/
# business_partnership/business_expansion are new (Phase 2 sub-intents) —
# see EVENT_SECONDARY_HOUSES below for the multi-house ones among them.
# "property" (Phase 5) is the 4th house — home/fixed-assets, the standard
# classical house for this question (the same convention already used here:
# one house + a karaka set, run through the same generic scanner).
EVENT_HOUSE: dict[EventType, int] = {
    "career": 10, "wealth": 2, "children": 5, "foreign_travel": 12,
    "career_promotion": 10, "business_partnership": 7, "business_expansion": 11,
    "property": 4,
}

# Secondary houses supporting a multi-house event, weighted below the
# primary house's own 3.0 base weight (see event_rules) — e.g. promotion's
# own house (career, 10th) is still the strongest signal; 11th (gains) and
# 2nd (accumulated wealth) are real but supporting classical evidence, not
# equal to the primary. Events not listed here (career/wealth/children/
# foreign_travel/business_partnership) are single-house, unchanged from
# before Phase 2.
EVENT_SECONDARY_HOUSES: dict[EventType, list[tuple[int, float]]] = {
    "career_promotion": [(11, 0.7), (2, 0.5)],
    "business_expansion": [(2, 0.6)],
}

# Classical significators (karakas) for each event, beyond the house lord
# itself — Saturn=karma/profession, Sun=authority/status, Jupiter/Venus=
# classical wealth significators, Jupiter alone=santan (children) karaka,
# Rahu=foreign lands/settlement, Jupiter=long journeys. Sourced from
# app.astro.event_karakas.CATEGORY_KARAKAS (which also registers marriage's
# karakas, for app.astro.marriage_timing) rather than duplicated here, so
# there's one place to update if a karaka set ever changes.
EVENT_KARAKAS: dict[EventType, list[PlanetKey]] = {
    event_type: list(CATEGORY_KARAKAS[event_type])
    for event_type in (
        "career", "wealth", "children", "foreign_travel",
        "career_promotion", "business_partnership", "business_expansion",
        "property",
    )
}


def event_rules(
    event_type: EventType,
    house_lord: PlanetKey,
    strength: dict[PlanetKey, float] | None = None,
    secondary_lords: dict[int, PlanetKey] | None = None,
) -> list[WindowRule]:
    """House-lord Antardasha is the strongest signal (the event's own house
    is directly activated); each karaka's Antardasha is an equally-weighted
    corroborating signal. The same at Mahadasha level is weaker backdrop-only
    weighting, same reasoning as marriage_timing.marriage_rules. If the
    house lord happens to BE one of the karakas, both rules fire on the same
    window — correctly a stronger signal, not double-counting.

    `strength` (see app.astro.natal_insights.significator_strength_multipliers)
    scales each rule's classical weight by how strong that significator
    actually is in this person's chart, same convention as
    marriage_timing.marriage_rules. Missing entries default to 1.0.

    Karaka rules (not the house-lord rules — the house lord is always
    category-specific by construction) are also scaled by
    app.astro.event_karakas.karaka_specificity_multiplier: Jupiter and
    Venus are each classical karakas for MULTIPLE categories here, so
    without this a single strong Jupiter/Venus Antardasha could win
    several unrelated categories from the same real dasha window — see
    that module's docstring for the empirical evidence this addresses.

    `secondary_lords` (Phase 2: `{house_number: lord}` for each of
    EVENT_SECONDARY_HOUSES.get(event_type, [])) adds a weaker supporting
    rule for a MULTI-house event like "career_promotion" (10th+11th+2nd) —
    weighted below the primary house-lord rule (see EVENT_SECONDARY_HOUSES'
    per-house multiplier), same karaka_specificity treatment as karaka
    rules since these are also real but non-primary evidence. Reason keys
    use "_secondary_house_{house}_antardasha" (no "house_lord"/"seventh_
    lord" substring), so _evidence_level classifies them as karaka-tier —
    correct: a supporting house's lord is real antardasha-level evidence,
    just not as strong as the event's own primary house lord."""
    strength = strength or {}
    secondary_lords = secondary_lords or {}

    def weight(planet: PlanetKey, base: float, karaka: bool = False) -> float:
        specificity = karaka_specificity_multiplier(planet) if karaka else 1.0
        return base * strength.get(planet, 1.0) * specificity

    rules = [
        WindowRule("antardasha_lord", house_lord, weight(house_lord, 3.0), f"{event_type}_house_lord_antardasha"),
        WindowRule("mahadasha_lord", house_lord, weight(house_lord, 1.0), f"{event_type}_house_lord_mahadasha"),
    ]
    for karaka in EVENT_KARAKAS[event_type]:
        rules.append(
            WindowRule(
                "antardasha_lord", karaka, weight(karaka, 2.0, karaka=True), f"{event_type}_karaka_antardasha_{karaka}"
            )
        )
        rules.append(
            WindowRule(
                "mahadasha_lord", karaka, weight(karaka, 0.5, karaka=True), f"{event_type}_karaka_mahadasha_{karaka}"
            )
        )
    for house, weight_mult in EVENT_SECONDARY_HOUSES.get(event_type, []):
        lord = secondary_lords.get(house)
        if lord is None:
            continue
        rules.append(
            WindowRule(
                "antardasha_lord", lord, weight(lord, 3.0 * weight_mult, karaka=True),
                f"{event_type}_secondary_house_{house}_antardasha",
            )
        )
        rules.append(
            WindowRule(
                "mahadasha_lord", lord, weight(lord, 1.0 * weight_mult, karaka=True),
                f"{event_type}_secondary_house_{house}_mahadasha",
            )
        )
    return rules


def find_event_windows(
    mahadashas: list[Mahadasha],
    event_type: EventType,
    house_lord: PlanetKey,
    from_dt: datetime,
    horizon_years: float = 20.0,
    top_n: int = 3,
    strength: dict[PlanetKey, float] | None = None,
    secondary_lords: dict[int, PlanetKey] | None = None,
) -> list[ScoredWindow]:
    """`weigh_dasha_relationship=True` (always on here) additionally scales
    each window by how the Antardasha lord classically relates to its
    Mahadasha lord, same convention as marriage_timing.find_marriage_windows
    — see app.astro.event_window_scanner.scan_dasha_windows. `secondary_lords`
    is passed straight through to event_rules — see its docstring."""
    scored = scan_dasha_windows(
        mahadashas, event_rules(event_type, house_lord, strength, secondary_lords), from_dt, horizon_years,
        weigh_dasha_relationship=True,
    )
    return scored[:top_n]


def corroborate_with_transits(
    event_type: EventType,
    window: ScoredWindow,
    lagna_sign_index: int,
    moon_sign_index: int,
    natal_planet_sign_index: dict[PlanetKey, int] | None = None,
) -> TransitCheck:
    """Whether any of this event's karakas transits its own house from Lagna
    or Moon during this window, how strong that specific transit's own
    Ashtakavarga support is, and independently whether a different malefic
    obstructs the same house at the same time — see
    app.astro.transit_corroboration for the full rules."""
    return check_transits(
        window, EVENT_HOUSE[event_type], tuple(EVENT_KARAKAS[event_type]),
        lagna_sign_index, moon_sign_index, natal_planet_sign_index,
    )
