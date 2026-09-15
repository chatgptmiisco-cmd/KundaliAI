from datetime import datetime, timedelta, timezone

import pytest

from app.astro.dasha import Antardasha, Mahadasha
from app.astro.marriage_timing import corroborate_with_transits, find_marriage_windows, marriage_rules
from app.astro.event_window_scanner import ScoredWindow
from app.astro.transit_corroboration import TransitCheck

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


def test_marriage_rules_score_seventh_lord_antardasha_highest():
    seventh_lord = "Sa"
    rules = marriage_rules(seventh_lord)
    antar_rule = next(r for r in rules if r.applies_to == "antardasha_lord" and r.target == seventh_lord)
    other_weights = [r.weight for r in rules if r.reason_key != antar_rule.reason_key]
    assert all(antar_rule.weight >= w for w in other_weights)


def test_marriage_rules_double_count_when_seventh_lord_is_a_karaka():
    # A chart whose 7th lord happens to be Venus fires BOTH the 7th-lord rule
    # and the Venus rule on the same Antardasha window — a genuinely stronger
    # signal, not a bug to suppress.
    rules_venus_seventh = marriage_rules("Ve")
    matching = [r for r in rules_venus_seventh if r.applies_to == "antardasha_lord" and r.target == "Ve"]
    assert len(matching) == 2  # the seventh_lord_antardasha rule AND venus_antardasha rule both target Ve
    assert {r.reason_key for r in matching} == {"seventh_lord_antardasha", "venus_antardasha"}


def test_find_marriage_windows_ranks_seventh_lord_window_above_unrelated_one():
    maha1 = _mahadasha("Sa", FROM, 19, ["Sa", "Me", "Ke"])  # Sa antardasha = 7th lord hit
    maha2 = _mahadasha("Me", maha1.end, 17, ["Me", "Ve", "Su"])
    timeline = [maha1, maha2]
    windows = find_marriage_windows(timeline, seventh_lord="Sa", from_dt=FROM, horizon_years=40, top_n=10)
    assert len(windows) > 0
    assert windows[0].antardasha_lord in ("Sa", "Ve")  # 7th lord or Venus antardasha ranks at the top
    # Every returned window has a positive score (irrelevant windows filtered out).
    assert all(w.score > 0 for w in windows)


def test_find_marriage_windows_respects_top_n():
    timeline = [_mahadasha("Ve", FROM, 20, ["Ve", "Su", "Mo", "Ma", "Ra", "Ju", "Sa", "Me", "Ke"])]
    windows = find_marriage_windows(timeline, seventh_lord="Ve", from_dt=FROM, horizon_years=25, top_n=2)
    assert len(windows) <= 2


def test_find_marriage_windows_searches_the_past_when_given_earlier_bounds():
    # No separate "past" function — get_marriage_timing's `direction="past"`
    # just calls this exact function with from_dt=birth_dt and
    # horizon_years=age instead of from_dt=now and horizon_years=20. This
    # confirms that choice of bounds genuinely searches (and bounds) the past.
    birth_dt = FROM
    now = FROM + timedelta(days=15 * 365.2425)  # "today" is 15 years after birth
    maha1 = _mahadasha("Sa", birth_dt, 19, ["Sa", "Me", "Ke"])
    age_years = (now - birth_dt).days / 365.2425

    windows = find_marriage_windows(
        [maha1], seventh_lord="Sa", from_dt=birth_dt, horizon_years=age_years, top_n=10
    )
    assert len(windows) > 0
    assert all(w.start >= birth_dt for w in windows)
    assert all(w.end <= now + timedelta(days=1) for w in windows)  # nothing beyond "now" returned


def test_marriage_rules_scales_weight_by_natal_strength():
    seventh_lord = "Sa"
    baseline = marriage_rules(seventh_lord)
    baseline_antar = next(r for r in baseline if r.applies_to == "antardasha_lord" and r.target == seventh_lord)
    baseline_venus = next(r for r in baseline if r.reason_key == "venus_antardasha")

    # A strong (exalted) 7th lord scores higher than the classical base weight;
    # Venus, untouched by `strength`, keeps its base weight unchanged.
    weighted = marriage_rules(seventh_lord, strength={"Sa": 1.5})
    weighted_antar = next(r for r in weighted if r.applies_to == "antardasha_lord" and r.target == seventh_lord)
    weighted_venus = next(r for r in weighted if r.reason_key == "venus_antardasha")
    assert weighted_antar.weight == pytest.approx(baseline_antar.weight * 1.5)
    assert weighted_venus.weight == baseline_venus.weight


def test_marriage_rules_missing_strength_entries_default_to_unchanged_weight():
    with_empty_strength = marriage_rules("Sa", strength={})
    without_strength = marriage_rules("Sa")
    assert [r.weight for r in with_empty_strength] == [r.weight for r in without_strength]


def test_find_marriage_windows_lets_a_weak_significator_be_outranked():
    # Venus and Jupiter Antardasha both carry the SAME classical base weight
    # (2.0, karaka-level) — with equal natal strength they'd tie. Scaling
    # Venus up (strong/unafflicted in this chart) and Jupiter down (weak)
    # should let Venus's window outrank Jupiter's despite the identical
    # classical rule.
    maha_ve = _mahadasha("Ve", FROM, 5, ["Ve"])
    maha_ju = _mahadasha("Ju", maha_ve.end, 5, ["Ju"])
    timeline = [maha_ve, maha_ju]

    windows = find_marriage_windows(
        timeline, seventh_lord="Su", from_dt=FROM, horizon_years=15, top_n=10,
        strength={"Ve": 1.5, "Ju": 0.5},
    )
    by_lord = {w.antardasha_lord: w for w in windows}
    assert by_lord["Ve"].score > by_lord["Ju"].score


def test_corroborate_with_transits_returns_a_transit_check():
    window = ScoredWindow(
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2027, 1, 1, tzinfo=timezone.utc),
        mahadasha_lord="Ve",
        antardasha_lord="Ve",
        score=2.0,
        reason_keys=["venus_antardasha"],
    )
    result = corroborate_with_transits(window, lagna_sign_index=0, moon_sign_index=3)
    assert isinstance(result, TransitCheck)
    assert isinstance(result.corroborated, bool)
    assert isinstance(result.obstructed, bool)
