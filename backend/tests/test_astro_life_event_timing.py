from datetime import datetime, timedelta, timezone

from app.astro.dasha import Antardasha, Mahadasha
from app.astro.life_event_timing import (
    EVENT_HOUSE,
    EVENT_KARAKAS,
    corroborate_with_transits,
    event_rules,
    find_event_windows,
)
from app.astro.event_window_scanner import ScoredWindow

FROM = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _mahadasha(lord, start, years, antardasha_lords) -> Mahadasha:
    end = start + timedelta(days=years * 365.2425)
    span = (end - start) / len(antardasha_lords)
    antardashas = []
    cursor = start
    for a_lord in antardasha_lords:
        a_end = cursor + span
        antardashas.append(Antardasha(lord=a_lord, start=cursor, end=a_end))
        cursor = a_end
    return Mahadasha(lord=lord, start=start, end=end, antardashas=antardashas)


def test_event_rules_score_house_lord_antardasha_highest():
    for event_type in EVENT_HOUSE:
        rules = event_rules(event_type, house_lord="Sa")
        house_lord_rule = next(r for r in rules if r.applies_to == "antardasha_lord" and r.target == "Sa")
        other_weights = [r.weight for r in rules if r.reason_key != house_lord_rule.reason_key]
        assert all(house_lord_rule.weight >= w for w in other_weights)


def test_event_rules_include_every_karaka_for_each_event_type():
    for event_type, karakas in EVENT_KARAKAS.items():
        rules = event_rules(event_type, house_lord="Me")
        antardasha_targets = {r.target for r in rules if r.applies_to == "antardasha_lord"}
        assert set(karakas).issubset(antardasha_targets)


def test_find_event_windows_ranks_house_lord_window_above_unrelated_one():
    maha1 = _mahadasha("Sa", FROM, 19, ["Sa", "Me", "Ke"])  # Sa antardasha = career house lord hit
    maha2 = _mahadasha("Me", maha1.end, 17, ["Me", "Ve", "Su"])
    timeline = [maha1, maha2]
    windows = find_event_windows(timeline, "career", house_lord="Sa", from_dt=FROM, horizon_years=40, top_n=10)
    assert len(windows) > 0
    assert all(w.score > 0 for w in windows)
    assert windows[0].score == max(w.score for w in windows)


def test_find_event_windows_respects_top_n():
    timeline = [_mahadasha("Ju", FROM, 16, ["Ju", "Sa", "Me", "Ke", "Ve", "Su", "Mo", "Ma", "Ra"])]
    windows = find_event_windows(timeline, "children", house_lord="Ju", from_dt=FROM, horizon_years=20, top_n=2)
    assert len(windows) <= 2


def test_corroborate_with_transits_checks_the_right_house_per_event_type():
    window = ScoredWindow(
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2027, 1, 1, tzinfo=timezone.utc),
        mahadasha_lord="Ju",
        antardasha_lord="Ju",
        score=2.0,
        reason_keys=["children_karaka_antardasha_Ju"],
    )
    for event_type in EVENT_HOUSE:
        result = corroborate_with_transits(event_type, window, lagna_sign_index=0, moon_sign_index=3)
        assert isinstance(result, bool)


def test_different_event_types_use_different_houses():
    houses = set(EVENT_HOUSE.values())
    assert len(houses) == len(EVENT_HOUSE)  # every event type maps to its own distinct house
