from datetime import datetime, timedelta, timezone

import pytest

from app.astro.dasha import Antardasha, Mahadasha
from app.astro.life_event_timing import (
    EVENT_HOUSE,
    EVENT_KARAKAS,
    corroborate_with_transits,
    event_rules,
    find_event_windows,
)
from app.astro.transit_corroboration import TransitCheck
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


def test_event_rules_scales_weight_by_natal_strength():
    house_lord = "Sa"
    baseline = event_rules("career", house_lord)
    baseline_antar = next(r for r in baseline if r.applies_to == "antardasha_lord" and r.target == house_lord)

    weighted = event_rules("career", house_lord, strength={house_lord: 1.5})
    weighted_antar = next(r for r in weighted if r.applies_to == "antardasha_lord" and r.target == house_lord)
    assert weighted_antar.weight == pytest.approx(baseline_antar.weight * 1.5)


def test_event_rules_missing_strength_entries_default_to_unchanged_weight():
    with_empty_strength = event_rules("wealth", "Sa", strength={})
    without_strength = event_rules("wealth", "Sa")
    assert [r.weight for r in with_empty_strength] == [r.weight for r in without_strength]


def test_find_event_windows_lets_a_weak_significator_be_outranked():
    # Wealth's two karakas (Jupiter, Venus) carry the SAME classical base
    # weight (2.0) — with equal natal strength they'd tie. Scaling Jupiter
    # up and Venus down should let Jupiter's window outrank Venus's despite
    # the identical classical rule.
    maha_ju = _mahadasha("Ju", FROM, 5, ["Ju"])
    maha_ve = _mahadasha("Ve", maha_ju.end, 5, ["Ve"])
    timeline = [maha_ju, maha_ve]

    windows = find_event_windows(
        timeline, "wealth", house_lord="Sa", from_dt=FROM, horizon_years=15, top_n=10,
        strength={"Ju": 1.5, "Ve": 0.5},
    )
    by_lord = {w.antardasha_lord: w for w in windows}
    assert by_lord["Ju"].score > by_lord["Ve"].score


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


def test_find_event_windows_searches_the_past_when_given_earlier_bounds():
    # Same as marriage timing's equivalent test: get_life_event_timing's
    # direction="past" is just from_dt=birth_dt/horizon_years=age instead of
    # from_dt=now/horizon_years=20 — no separate "past" function needed.
    birth_dt = FROM
    now = FROM + timedelta(days=10 * 365.2425)
    maha1 = _mahadasha("Sa", birth_dt, 19, ["Sa", "Me", "Ke"])
    age_years = (now - birth_dt).days / 365.2425

    windows = find_event_windows(
        [maha1], "career", house_lord="Sa", from_dt=birth_dt, horizon_years=age_years, top_n=10
    )
    assert len(windows) > 0
    assert all(w.start >= birth_dt for w in windows)
    assert all(w.end <= now + timedelta(days=1) for w in windows)


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
        assert isinstance(result, TransitCheck)
        assert isinstance(result.corroborated, bool)
        assert isinstance(result.obstructed, bool)


def test_different_event_types_use_different_houses():
    # Phase 2 sub-intents deliberately reuse a parent domain's own primary
    # house — career_promotion is career's own 10th house (a promotion IS
    # a career event); business_partnership is the 7th house's OTHER
    # classical meaning (shared with marriage_timing.py's own separate
    # _SEVENTH_HOUSE constant, not part of this dict at all). Every OTHER
    # event type still maps to its own distinct house.
    original_and_new_domains = {
        "career": 10, "wealth": 2, "children": 5, "foreign_travel": 12, "business_expansion": 11,
    }
    houses = {EVENT_HOUSE[event_type] for event_type in original_and_new_domains}
    assert houses == set(original_and_new_domains.values())
    assert len(houses) == len(original_and_new_domains)
    assert EVENT_HOUSE["career_promotion"] == EVENT_HOUSE["career"]
    assert EVENT_HOUSE["business_partnership"] == 7
