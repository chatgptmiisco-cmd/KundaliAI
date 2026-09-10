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
from datetime import datetime, timedelta
from typing import Literal

from app.astro.constants import PlanetKey
from app.astro.dasha import Mahadasha
from app.astro.event_window_scanner import ScoredWindow, WindowRule, scan_dasha_windows
from app.astro.transits import compute_transit_snapshot

EventType = Literal["career", "wealth", "children", "foreign_travel"]

# The house each event classically activates.
EVENT_HOUSE: dict[EventType, int] = {"career": 10, "wealth": 2, "children": 5, "foreign_travel": 12}

# Classical significators (karakas) for each event, beyond the house lord itself.
EVENT_KARAKAS: dict[EventType, list[PlanetKey]] = {
    "career": ["Sa", "Su"],  # Saturn = karma/profession karaka, Sun = authority/status
    "wealth": ["Ju", "Ve"],  # classical wealth significators
    "children": ["Ju"],  # Jupiter = santan (children) karaka
    "foreign_travel": ["Ra", "Ju"],  # Rahu = foreign lands/settlement, Jupiter = long journeys
}


def event_rules(event_type: EventType, house_lord: PlanetKey) -> list[WindowRule]:
    """House-lord Antardasha is the strongest signal (the event's own house
    is directly activated); each karaka's Antardasha is an equally-weighted
    corroborating signal. The same at Mahadasha level is weaker backdrop-only
    weighting, same reasoning as marriage_timing.marriage_rules. If the
    house lord happens to BE one of the karakas, both rules fire on the same
    window — correctly a stronger signal, not double-counting."""
    rules = [
        WindowRule("antardasha_lord", house_lord, 3.0, f"{event_type}_house_lord_antardasha"),
        WindowRule("mahadasha_lord", house_lord, 1.0, f"{event_type}_house_lord_mahadasha"),
    ]
    for karaka in EVENT_KARAKAS[event_type]:
        rules.append(WindowRule("antardasha_lord", karaka, 2.0, f"{event_type}_karaka_antardasha_{karaka}"))
        rules.append(WindowRule("mahadasha_lord", karaka, 0.5, f"{event_type}_karaka_mahadasha_{karaka}"))
    return rules


def find_event_windows(
    mahadashas: list[Mahadasha],
    event_type: EventType,
    house_lord: PlanetKey,
    from_dt: datetime,
    horizon_years: float = 20.0,
    top_n: int = 3,
) -> list[ScoredWindow]:
    scored = scan_dasha_windows(mahadashas, event_rules(event_type, house_lord), from_dt, horizon_years)
    return scored[:top_n]


def corroborate_with_transits(
    event_type: EventType, window: ScoredWindow, lagna_sign_index: int, moon_sign_index: int
) -> bool:
    """Samples each karaka's transiting position at the window's start,
    midpoint, and end (monthly-scale granularity — karakas here are all
    slow-to-moderate movers) and reports whether any transits the event's
    own house from Lagna or Moon at any of those points."""
    house = EVENT_HOUSE[event_type]
    karakas = EVENT_KARAKAS[event_type]
    span = window.end - window.start
    sample_points = [window.start, window.start + span / 2, window.end - timedelta(seconds=1)]
    for at in sample_points:
        snapshot = compute_transit_snapshot(at, lagna_sign_index, moon_sign_index)
        for karaka in karakas:
            if snapshot.planet_house_from_lagna.get(karaka) == house:
                return True
            if snapshot.planet_house_from_moon.get(karaka) == house:
                return True
    return False
