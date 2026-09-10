"""Unit tests for the pure `_build_focus_readings` function — every expected
value below is hand-derived from the same fixture used in
test_daily_reading_service.py, so the natal facts (dignity, house lords) are
already independently verified there."""
from datetime import datetime, timezone

from app.astro.natal_insights import compute_natal_insights
from app.astro.transits import TransitSnapshot
from app.services.focus_reading_service import _build_focus_readings

_LAGNA_SIGN_INDEX = 0  # Aries
_NATAL_SIGN_INDEX = {"Su": 2, "Mo": 3, "Ma": 7, "Me": 2, "Ju": 8, "Ve": 1, "Sa": 6, "Ra": 0, "Ke": 6}
_NATAL_HOUSE = {"Su": 3, "Mo": 4, "Ma": 8, "Me": 3, "Ju": 9, "Ve": 2, "Sa": 7, "Ra": 1, "Ke": 7}


def _fixture_insights():
    return compute_natal_insights(_LAGNA_SIGN_INDEX, _NATAL_SIGN_INDEX, _NATAL_HOUSE)


def _fake_snapshot() -> TransitSnapshot:
    house_from_lagna = {"Su": 5, "Mo": 1, "Ma": 9, "Me": 5, "Ju": 4, "Ve": 6, "Sa": 8, "Ra": 3, "Ke": 9}
    return TransitSnapshot(
        at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        planet_sign_index={k: 0 for k in house_from_lagna},
        planet_house_from_lagna=house_from_lagna,
        planet_house_from_moon=dict(house_from_lagna),
        planet_retrograde={k: False for k in house_from_lagna},
    )


def _readings_by_area(language: str = "en"):
    readings = _build_focus_readings(
        language=language,
        insights=_fixture_insights(),
        transit_snapshot=_fake_snapshot(),
        sun_longitude_today=10.0,
        moon_longitude_today=100.0,  # diff=90 -> tithi index 8 (matches test_daily_reading_service.py)
    )
    return {r["area"]: r for r in readings}


def test_all_five_areas_present_with_correct_houses():
    by_area = _readings_by_area()
    assert by_area["family"]["house"] == 4
    assert by_area["health"]["house"] == 6
    assert by_area["career"]["house"] == 10
    assert by_area["marriage_relationships"]["house"] == 7
    assert by_area["friends"]["house"] == 11


def test_house_lords_and_dignity_are_real_chart_facts():
    by_area = _readings_by_area()
    # House 4 (Cancer) -> Moon, in its own sign here (Moon natally in Cancer).
    assert by_area["family"]["house_lord"] == "Mo"
    assert by_area["family"]["dignity"] == "own_sign"
    assert by_area["family"]["house_lord_house"] == 4  # Moon sits in its own 4th house

    # House 10 (Capricorn) and house 11 (Aquarius) share the same lord (Saturn),
    # which is exalted in this chart (Libra) -> both areas reflect that.
    assert by_area["career"]["house_lord"] == "Sa"
    assert by_area["friends"]["house_lord"] == "Sa"
    assert by_area["career"]["dignity"] == "exalted"
    assert by_area["friends"]["dignity"] == "exalted"


def test_rating_reflects_dignity_house_placement_and_todays_transit():
    by_area = _readings_by_area()
    # Family: Moon own-sign (+2) + lord in a growth house (+1) + Jupiter (benefic)
    # transiting house 4 today (+1) -> base 6 + 2 + 1 + 1 = 10.
    assert by_area["family"]["rating"] == 10
    assert by_area["family"]["transit_note"] is not None
    assert "Jupiter" in by_area["family"]["transit_note"]
    # Jupiter is a benefic transit here — the note must say what that means
    # (real progress), not just the bare fact that it's passing through.
    assert "progress" in by_area["family"]["transit_note"]

    # Career: nothing transits house 10 in this snapshot -> no transit note,
    # but exalted dignity (+3) + growth-house placement (+1) still applies.
    assert by_area["career"]["transit_note"] is None
    assert by_area["career"]["rating"] == 10

    # Marriage/relationships: Venus own-sign (+2), lord's own house (2) is
    # neither dusthana nor growth -> no placement bonus, nothing transits
    # house 7 today -> rating stays at the dignity-only level.
    assert by_area["marriage_relationships"]["rating"] == 8
    assert by_area["marriage_relationships"]["transit_note"] is None


def test_ratings_are_always_within_bounds():
    by_area = _readings_by_area()
    for reading in by_area.values():
        assert 1 <= reading["rating"] <= 10


def test_meaning_reflects_dignity_not_just_lord():
    by_area = _readings_by_area()
    # Career's lord (Saturn) is exalted here -> "meaning" should draw on the
    # real per-chart strength framing, not a generic placeholder.
    assert by_area["career"]["meaning"]
    assert "Saturn" in by_area["career"]["meaning"]


def test_avoid_and_focus_today_are_populated_and_area_specific():
    by_area = _readings_by_area()
    for reading in by_area.values():
        assert reading["avoid_today"]
        assert reading["focus_today"]
        assert reading["theme"].lower() in reading["avoid_today"].lower()
        assert reading["theme"].lower() in reading["focus_today"].lower()


def test_hindi_language_produces_devanagari_text():
    by_area = _readings_by_area(language="hi")
    for reading in by_area.values():
        for field in ("summary", "meaning", "avoid_today", "focus_today"):
            assert reading[field]
            assert any(ord(ch) > 128 for ch in reading[field])  # contains non-ASCII (Devanagari) text
