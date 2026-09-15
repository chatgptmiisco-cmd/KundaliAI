"""Marriage-timing prediction: a classical rule set (the 7th-house lord's own
dasha period, Venus/Jupiter dasha periods — the traditional marriage
karakas/significators) run through the generic window scanner
(app.astro.event_window_scanner), plus a transit-corroboration check.

This produces a ranked list of *probable favorable windows* for marriage or
a serious partnership — not a fabricated exact date. That's genuinely how a
real astrologer reasons about timing, and it's consistent with this app's
rule against inventing false precision.
"""
from datetime import datetime

from app.astro.constants import PlanetKey
from app.astro.dasha import Mahadasha
from app.astro.event_karakas import karaka_specificity_multiplier
from app.astro.event_window_scanner import ScoredWindow, WindowRule, scan_dasha_windows
from app.astro.transit_corroboration import TransitCheck, check_transits

_SEVENTH_HOUSE = 7
_CORROBORATING_PLANETS: tuple[PlanetKey, ...] = ("Ju", "Sa")


def marriage_rules(
    seventh_lord: PlanetKey, strength: dict[PlanetKey, float] | None = None
) -> list[WindowRule]:
    """7th-lord Antardasha is the strongest classical signal (the house of
    partnership itself is activated); Venus/Jupiter Antardasha are the
    traditional marriage karakas and count as corroborating signals of equal
    weight. The same three at Mahadasha level are weaker backdrop-only
    signals — a Mahadasha can run for years, so simply being inside one
    doesn't pin down timing the way its own Antardasha does.

    If the chart's own 7th lord happens to BE Venus or Jupiter, both rules
    fire together on the same window — correctly a stronger signal, not
    double-counting a bug.

    `strength` (see app.astro.natal_insights.significator_strength_multipliers)
    scales each rule's classical weight by how strong that significator
    actually is in this person's chart — an exalted, unafflicted 7th lord's
    Antardasha is a stronger real signal than the same rule firing for a
    debilitated, combust one. Missing entries default to 1.0 (no change),
    so passing nothing reproduces the pre-strength-weighting behavior.

    Venus/Jupiter's karaka rules (not the 7th-lord rule — the house lord is
    always category-specific by construction) are also scaled by
    app.astro.event_karakas.karaka_specificity_multiplier: both are
    classical karakas for OTHER categories too (Venus for wealth, Jupiter
    for wealth/children/foreign_travel), so a strong Venus/Jupiter
    Antardasha used to be able to win marriage, wealth, children, and
    foreign-travel timing all from the same real dasha window — verified
    empirically as a real, common pattern (78% of a 20-chart test's
    user/direction combinations shared a duplicate #1 window across
    categories), not merely a hypothetical concern."""
    strength = strength or {}

    def weight(planet: PlanetKey, base: float, karaka: bool = False) -> float:
        specificity = karaka_specificity_multiplier(planet) if karaka else 1.0
        return base * strength.get(planet, 1.0) * specificity

    return [
        WindowRule("antardasha_lord", seventh_lord, weight(seventh_lord, 3.0), "seventh_lord_antardasha"),
        WindowRule("antardasha_lord", "Ve", weight("Ve", 2.0, karaka=True), "venus_antardasha"),
        WindowRule("antardasha_lord", "Ju", weight("Ju", 2.0, karaka=True), "jupiter_antardasha"),
        WindowRule("mahadasha_lord", seventh_lord, weight(seventh_lord, 1.0), "seventh_lord_mahadasha"),
        WindowRule("mahadasha_lord", "Ve", weight("Ve", 0.5, karaka=True), "venus_mahadasha"),
        WindowRule("mahadasha_lord", "Ju", weight("Ju", 0.5, karaka=True), "jupiter_mahadasha"),
    ]


def find_marriage_windows(
    mahadashas: list[Mahadasha],
    seventh_lord: PlanetKey,
    from_dt: datetime,
    horizon_years: float = 20.0,
    top_n: int = 3,
    strength: dict[PlanetKey, float] | None = None,
) -> list[ScoredWindow]:
    """`weigh_dasha_relationship=True` (always on here) additionally scales
    each window by how the Antardasha lord classically relates to its
    Mahadasha lord — same planet, natural friend, or natural enemy — on top
    of the classical rule score and the `strength` natal-dignity scaling
    above. See app.astro.event_window_scanner.scan_dasha_windows."""
    scored = scan_dasha_windows(
        mahadashas, marriage_rules(seventh_lord, strength), from_dt, horizon_years,
        weigh_dasha_relationship=True,
    )
    return scored[:top_n]


def corroborate_with_transits(
    window: ScoredWindow,
    lagna_sign_index: int,
    moon_sign_index: int,
    natal_planet_sign_index: dict[PlanetKey, int] | None = None,
) -> TransitCheck:
    """Whether Jupiter or Saturn transits the 7th house from Lagna or Moon
    during this window (a classical corroborating signal for relationship-
    house activation), how strong that specific transit's own Ashtakavarga
    support is, and independently whether a different malefic obstructs the
    same house at the same time — see app.astro.transit_corroboration for
    the full rules."""
    return check_transits(
        window, _SEVENTH_HOUSE, _CORROBORATING_PLANETS, lagna_sign_index, moon_sign_index, natal_planet_sign_index
    )
