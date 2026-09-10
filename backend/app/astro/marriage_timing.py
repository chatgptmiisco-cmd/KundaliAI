"""Marriage-timing prediction: a classical rule set (the 7th-house lord's own
dasha period, Venus/Jupiter dasha periods — the traditional marriage
karakas/significators) run through the generic window scanner
(app.astro.event_window_scanner), plus a transit-corroboration check.

This produces a ranked list of *probable favorable windows* for marriage or
a serious partnership — not a fabricated exact date. That's genuinely how a
real astrologer reasons about timing, and it's consistent with this app's
rule against inventing false precision.
"""
from datetime import datetime, timedelta

from app.astro.constants import PlanetKey
from app.astro.dasha import Mahadasha
from app.astro.event_window_scanner import ScoredWindow, WindowRule, scan_dasha_windows
from app.astro.transits import compute_transit_snapshot

_SEVENTH_HOUSE = 7


def marriage_rules(seventh_lord: PlanetKey) -> list[WindowRule]:
    """7th-lord Antardasha is the strongest classical signal (the house of
    partnership itself is activated); Venus/Jupiter Antardasha are the
    traditional marriage karakas and count as corroborating signals of equal
    weight. The same three at Mahadasha level are weaker backdrop-only
    signals — a Mahadasha can run for years, so simply being inside one
    doesn't pin down timing the way its own Antardasha does.

    If the chart's own 7th lord happens to BE Venus or Jupiter, both rules
    fire together on the same window — correctly a stronger signal, not
    double-counting a bug."""
    return [
        WindowRule("antardasha_lord", seventh_lord, 3.0, "seventh_lord_antardasha"),
        WindowRule("antardasha_lord", "Ve", 2.0, "venus_antardasha"),
        WindowRule("antardasha_lord", "Ju", 2.0, "jupiter_antardasha"),
        WindowRule("mahadasha_lord", seventh_lord, 1.0, "seventh_lord_mahadasha"),
        WindowRule("mahadasha_lord", "Ve", 0.5, "venus_mahadasha"),
        WindowRule("mahadasha_lord", "Ju", 0.5, "jupiter_mahadasha"),
    ]


def find_marriage_windows(
    mahadashas: list[Mahadasha],
    seventh_lord: PlanetKey,
    from_dt: datetime,
    horizon_years: float = 20.0,
    top_n: int = 3,
) -> list[ScoredWindow]:
    scored = scan_dasha_windows(mahadashas, marriage_rules(seventh_lord), from_dt, horizon_years)
    return scored[:top_n]


def corroborate_with_transits(window: ScoredWindow, lagna_sign_index: int, moon_sign_index: int) -> bool:
    """Samples Jupiter/Saturn's transiting position at the window's start,
    midpoint, and end (monthly-scale granularity is enough — both are slow
    movers) and reports whether either transits the 7th house from Lagna or
    Moon at any of those points — a classical corroborating signal for
    relationship-house activation during this window."""
    span = window.end - window.start
    sample_points = [window.start, window.start + span / 2, window.end - timedelta(seconds=1)]
    for at in sample_points:
        snapshot = compute_transit_snapshot(at, lagna_sign_index, moon_sign_index)
        if snapshot.planet_house_from_lagna.get("Ju") == _SEVENTH_HOUSE:
            return True
        if snapshot.planet_house_from_lagna.get("Sa") == _SEVENTH_HOUSE:
            return True
        if snapshot.planet_house_from_moon.get("Ju") == _SEVENTH_HOUSE:
            return True
        if snapshot.planet_house_from_moon.get("Sa") == _SEVENTH_HOUSE:
            return True
    return False
