from datetime import datetime, timezone

import pytest

from app.astro import transit_corroboration
from app.astro.event_window_scanner import ScoredWindow
from app.astro.transit_corroboration import TransitCheck, check_transits
from app.astro.transits import TransitSnapshot

WINDOW = ScoredWindow(
    start=datetime(2026, 1, 1, tzinfo=timezone.utc),
    end=datetime(2027, 1, 1, tzinfo=timezone.utc),
    mahadasha_lord="Sa",
    antardasha_lord="Me",
    score=3.0,
    reason_keys=[],
)


def _snapshot(planet_house_from_lagna: dict, planet_sign_index: dict | None = None) -> TransitSnapshot:
    return TransitSnapshot(
        at=WINDOW.start,
        planet_sign_index=planet_sign_index or {},
        planet_house_from_lagna=planet_house_from_lagna,
        planet_house_from_moon={},
        planet_retrograde={},
    )


def _patch_snapshots(monkeypatch, snapshots: list[TransitSnapshot]):
    calls = iter(snapshots)
    monkeypatch.setattr(transit_corroboration, "compute_transit_snapshot", lambda at, lagna, moon: next(calls))


def test_check_transits_reports_no_corroboration_or_obstruction_when_nothing_relevant_is_there(monkeypatch):
    empty = _snapshot({})
    _patch_snapshots(monkeypatch, [empty, empty, empty])
    result = check_transits(WINDOW, target_house=7, corroborating_planets=("Ju", "Sa"), lagna_sign_index=0, moon_sign_index=3)
    assert result == TransitCheck(
        corroborated=False, corroboration_strength=1.0, corroborating_planet=None,
        obstructed=False, obstructing_planet=None, obstruction_fraction=0.0,
    )


def test_check_transits_reports_corroboration_when_a_listed_planet_occupies_the_target_house(monkeypatch):
    hit = _snapshot({"Ju": 7}, {"Ju": 0})
    _patch_snapshots(monkeypatch, [hit, hit, hit])
    result = check_transits(WINDOW, target_house=7, corroborating_planets=("Ju", "Sa"), lagna_sign_index=0, moon_sign_index=3)
    assert result.corroborated is True
    assert result.corroborating_planet == "Ju"


def test_check_transits_ignores_a_planet_not_in_the_corroborating_list(monkeypatch):
    # Mercury occupies the target house, but it's not one of the
    # corroborating planets passed in — no corroboration should fire.
    hit = _snapshot({"Me": 7}, {"Me": 0})
    _patch_snapshots(monkeypatch, [hit, hit, hit])
    result = check_transits(WINDOW, target_house=7, corroborating_planets=("Ju", "Sa"), lagna_sign_index=0, moon_sign_index=3)
    assert result.corroborated is False


def test_check_transits_scales_corroboration_strength_by_ashtakavarga_when_natal_data_given():
    # Real (non-monkeypatched) Ashtakavarga computation: build a natal chart
    # where we know Saturn's own BAV bindu count at a specific sign, then
    # directly verify check_transits applies the matching multiplier.
    from app.astro.ashtakavarga import ashtakavarga_strength_multiplier, compute_bav

    natal = {"Su": 8, "Mo": 6, "Ma": 10, "Me": 8, "Ju": 0, "Ve": 7, "Sa": 0}
    bav_sa = compute_bav("Sa", natal, natal_lagna_sign_index=8)
    # Pick whichever sign has the fewest bindus so the test is robust to any
    # future edit of the classical table, rather than hardcoding one.
    weak_sign = min(bav_sa, key=bav_sa.get)
    expected_multiplier = ashtakavarga_strength_multiplier(bav_sa[weak_sign])

    import app.astro.transit_corroboration as tc_module

    hit = TransitSnapshot(
        at=WINDOW.start, planet_sign_index={"Sa": weak_sign},
        planet_house_from_lagna={"Sa": 7}, planet_house_from_moon={}, planet_retrograde={},
    )
    original = tc_module.compute_transit_snapshot
    tc_module.compute_transit_snapshot = lambda at, lagna, moon: hit
    try:
        result = check_transits(
            WINDOW, target_house=7, corroborating_planets=("Sa",),
            lagna_sign_index=8, moon_sign_index=6, natal_planet_sign_index=natal,
        )
    finally:
        tc_module.compute_transit_snapshot = original

    assert result.corroborated is True
    assert result.corroboration_strength == expected_multiplier


def test_check_transits_defaults_corroboration_strength_to_one_without_natal_data(monkeypatch):
    hit = _snapshot({"Sa": 7}, {"Sa": 0})
    _patch_snapshots(monkeypatch, [hit, hit, hit])
    result = check_transits(
        WINDOW, target_house=7, corroborating_planets=("Sa",), lagna_sign_index=0, moon_sign_index=3,
        natal_planet_sign_index=None,
    )
    assert result.corroborated is True
    assert result.corroboration_strength == 1.0


def test_check_transits_never_computes_ashtakavarga_for_rahu_or_ketu(monkeypatch):
    # Rahu/Ketu have no Ashtakavarga table — corroboration_strength must
    # stay at the neutral 1.0 even when full natal data IS supplied.
    natal = {"Su": 8, "Mo": 6, "Ma": 10, "Me": 8, "Ju": 0, "Ve": 7, "Sa": 0}
    hit = _snapshot({"Ra": 7}, {"Ra": 3})
    _patch_snapshots(monkeypatch, [hit, hit, hit])
    result = check_transits(
        WINDOW, target_house=7, corroborating_planets=("Ra", "Ju"), lagna_sign_index=8, moon_sign_index=6,
        natal_planet_sign_index=natal,
    )
    assert result.corroborated is True
    assert result.corroborating_planet == "Ra"
    assert result.corroboration_strength == 1.0


def test_check_transits_reports_obstruction_from_a_different_malefic_occupying_the_target_house(monkeypatch):
    hit = _snapshot({"Ma": 7}, {"Ma": 0})
    _patch_snapshots(monkeypatch, [hit, hit, hit])
    result = check_transits(WINDOW, target_house=7, corroborating_planets=("Ju", "Sa"), lagna_sign_index=0, moon_sign_index=3)
    assert result.obstructed is True
    assert result.obstructing_planet == "Ma"
    assert result.obstruction_fraction == pytest.approx(1.0)


def test_check_transits_obstruction_fraction_is_graded_not_binary(monkeypatch):
    # A single hit out of 3 sample points is a real but fleeting signal —
    # obstruction_fraction should reflect that (1/3), not collapse to the
    # same "obstructed" verdict as a hit on all 3 points.
    hit = _snapshot({"Ma": 7}, {"Ma": 0})
    miss = _snapshot({}, {})
    _patch_snapshots(monkeypatch, [hit, miss, miss])
    result = check_transits(WINDOW, target_house=7, corroborating_planets=("Ju", "Sa"), lagna_sign_index=0, moon_sign_index=3)
    assert result.obstructed is True
    assert result.obstruction_fraction == pytest.approx(1 / 3)


def test_check_transits_obstruction_is_checked_at_every_point_even_after_corroboration_found(monkeypatch):
    # Corroboration is found at the FIRST point and never rechecked — but
    # obstruction must still be checked at all 3 points regardless, since
    # its fraction depends on every point, not just the ones before
    # corroboration happened to resolve.
    first = _snapshot({"Ju": 7, "Ma": 7}, {"Ju": 0, "Ma": 1})
    later_obstruction_only = _snapshot({"Ma": 7}, {"Ma": 1})
    _patch_snapshots(monkeypatch, [first, later_obstruction_only, later_obstruction_only])
    result = check_transits(WINDOW, target_house=7, corroborating_planets=("Ju", "Sa"), lagna_sign_index=0, moon_sign_index=3)
    assert result.corroborated is True
    assert result.obstruction_fraction == pytest.approx(1.0)  # all 3 points had Mars there


def test_check_transits_excludes_corroborating_planets_from_obstruction_candidates(monkeypatch):
    # Saturn occupies the target house — since Saturn IS one of the
    # corroborating planets for this call, it must count as corroboration,
    # never as obstruction (no double-counting one transit under
    # contradictory labels).
    hit = _snapshot({"Sa": 7}, {"Sa": 0})
    _patch_snapshots(monkeypatch, [hit, hit, hit])
    result = check_transits(WINDOW, target_house=7, corroborating_planets=("Ju", "Sa"), lagna_sign_index=0, moon_sign_index=3)
    assert result.corroborated is True
    assert result.obstructed is False


def test_check_transits_only_occupancy_not_aspect_counts_as_obstruction(monkeypatch):
    # Saturn (a special-aspect planet) sitting in house 4 casts its
    # classical 10th-house special aspect onto house 1 — but obstruction
    # requires actual occupancy, not merely an aspect (see the module
    # docstring for why), so this must NOT be reported as obstruction of
    # house 1.
    snapshot = _snapshot({"Sa": 4}, {"Sa": 0})
    _patch_snapshots(monkeypatch, [snapshot, snapshot, snapshot])
    result = check_transits(WINDOW, target_house=1, corroborating_planets=("Ju",), lagna_sign_index=0, moon_sign_index=3)
    assert result.obstructed is False
