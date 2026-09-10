import pytest

from app.services.interpretation.prediction_templates import (
    marriage_window_reason_text,
    overall_year_theme,
    year_outlook_text,
    year_rating,
)


@pytest.mark.parametrize("language", ["en", "hi"])
def test_year_outlook_text_varies_by_real_dignity_and_house(language):
    strong = year_outlook_text(
        antardasha_lord="Ju", antardasha_lord_house=10, antardasha_lord_dignity="exalted",
        varsheshwar="Ve", varsheshwar_dignity="own_sign", muntha_house=11,
        jupiter_transit_house_from_moon=11, saturn_transit_house_from_moon=3,
        active_dosha_notes=[], language=language,
    )
    weak = year_outlook_text(
        antardasha_lord="Sa", antardasha_lord_house=8, antardasha_lord_dignity="debilitated",
        varsheshwar="Ma", varsheshwar_dignity="debilitated", muntha_house=12,
        jupiter_transit_house_from_moon=6, saturn_transit_house_from_moon=8,
        active_dosha_notes=["Saturn's Sade Sati is in its peak phase during this stretch."], language=language,
    )
    assert strong["theme"] != weak["theme"]
    assert strong["rating"] > weak["rating"]
    assert strong["opportunities"]
    assert weak["risks"]


def test_year_outlook_text_includes_dosha_notes_in_risks():
    note = "Saturn's Sade Sati is in its peak phase during this stretch."
    result = year_outlook_text(
        antardasha_lord="Mo", antardasha_lord_house=5, antardasha_lord_dignity="neutral",
        varsheshwar="Su", varsheshwar_dignity="neutral", muntha_house=3,
        jupiter_transit_house_from_moon=4, saturn_transit_house_from_moon=1,
        active_dosha_notes=[note], language="en",
    )
    assert note in result["risks"]


@pytest.mark.parametrize("language", ["en", "hi"])
def test_year_outlook_text_differs_by_transit_houses_even_with_identical_dasha_and_varshaphala_facts(language):
    """Regression guard: if the same Antardasha runs a whole year (common —
    some last several years), quarters must still read differently thanks to
    Jupiter/Saturn's own slower transit movement, not collapse to one
    repeated block."""
    common = dict(
        antardasha_lord="Ju", antardasha_lord_house=7, antardasha_lord_dignity="neutral",
        varsheshwar="Me", varsheshwar_dignity="neutral", muntha_house=9,
        active_dosha_notes=[], language=language,
    )
    q1 = year_outlook_text(jupiter_transit_house_from_moon=2, saturn_transit_house_from_moon=5, **common)
    q2 = year_outlook_text(jupiter_transit_house_from_moon=3, saturn_transit_house_from_moon=6, **common)
    assert q1["theme"] != q2["theme"]


def test_year_rating_rewards_strong_dignity_and_supportive_muntha():
    high = year_rating("exalted", "own_sign", muntha_house=10, active_dosha_count=0)
    low = year_rating("debilitated", "debilitated", muntha_house=8, active_dosha_count=2)
    assert 1 <= low <= high <= 10
    assert high > low


def test_year_rating_is_bounded():
    assert year_rating("exalted", "exalted", muntha_house=11, active_dosha_count=0) <= 10
    assert year_rating("debilitated", "debilitated", muntha_house=12, active_dosha_count=5) >= 1


@pytest.mark.parametrize("language", ["en", "hi"])
def test_overall_year_theme_varies_by_varsheshwar_and_muntha(language):
    a = overall_year_theme("Ju", "exalted", 10, language)
    b = overall_year_theme("Sa", "debilitated", 6, language)
    assert a != b
    assert len(a) > 10 and len(b) > 10


@pytest.mark.parametrize("language", ["en", "hi"])
def test_marriage_window_reason_text_composes_multiple_reasons(language):
    text = marriage_window_reason_text(
        reason_keys=["seventh_lord_antardasha", "venus_antardasha"],
        seventh_lord_name="Venus" if language == "en" else "शुक्र",
        transit_corroborated=True,
        language=language,
    )
    assert "Venus" in text or "शुक्र" in text
    if language == "en":
        assert "Jupiter or Saturn" in text
    else:
        assert "गुरु या शनि" in text


def test_marriage_window_reason_text_omits_corroboration_when_absent():
    text = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus", transit_corroborated=False, language="en",
    )
    assert "Jupiter or Saturn" not in text
