"""Coverage for app.services.business_suitability_service — deterministic,
multi-signal "does THIS business type suit me" assessment. No provider
calls. See the plan's Phase 7: never a single `strongest_planet ==
business_planet` binary rule, and never a fabricated astrology signal (the
codebase has no dedicated "wealth yoga" detector — only checked here for the
two REAL, already-detected general success/prosperity yogas, Raj Yoga and
Gajakesari)."""
from app.services.business_suitability_service import assess_business_category_suitability


def test_known_category_matches_its_classical_planet_bucket():
    result = assess_business_category_suitability(
        "clothing", strongest_planet_code="Ve", house_verdict_bucket={}, yogas=[], business_start_decision=None,
    )
    assert result["category_recognized"] is True
    assert result["matched_bucket"] == "Ve"
    assert result["planet_alignment"] == "supportive"


def test_unrecognized_category_is_honest_about_insufficient_data():
    """A business type the keyword table has no bucket for must never be
    silently substituted with a generic career-timing read."""
    result = assess_business_category_suitability(
        "underwater basket weaving", strongest_planet_code="Ve", house_verdict_bucket={2: "favorable"}, yogas=[],
        business_start_decision={"verdict": "favorable"},
    )
    assert result["category_recognized"] is False
    assert result["matched_bucket"] is None
    assert result["overall"] == "insufficient_data"


def test_conflicting_signals_produce_a_mixed_verdict_not_a_forced_pick():
    """Planet alignment says challenging (matched bucket is the weakest
    planet) while the wealth houses read favorable, with no yoga to break
    the tie — one supportive signal and one challenging signal must land on
    "mixed", never an arbitrarily forced pick either way."""
    result = assess_business_category_suitability(
        "steel manufacturing plant",
        strongest_planet_code="Ve",
        weakest_planet_code="Ma",
        house_verdict_bucket={2: "favorable", 7: "favorable", 11: "favorable"},
        yogas=[],
        business_start_decision=None,
    )
    assert result["matched_bucket"] == "Ma"
    assert result["planet_alignment"] == "challenging"
    assert result["wealth_house_signal"] == "supportive"
    assert result["supportive_yoga_present"] is False
    assert result["overall"] == "mixed"


def test_two_agreeing_supportive_signals_outvote_a_single_challenging_one():
    result = assess_business_category_suitability(
        "steel manufacturing plant",
        strongest_planet_code="Ve",
        weakest_planet_code="Ma",
        house_verdict_bucket={2: "favorable", 7: "favorable", 11: "favorable"},
        yogas=[{"key": "raj_yoga"}],
        business_start_decision=None,
    )
    assert result["overall"] == "supportive"


def test_timing_signal_is_passed_through_from_business_start_decision_unchanged():
    result = assess_business_category_suitability(
        "consulting", strongest_planet_code=None, house_verdict_bucket={}, yogas=[],
        business_start_decision={"verdict": "wait_for_better_window"},
    )
    assert result["timing_signal"] == "wait_for_better_window"


def test_only_real_detected_yogas_count_as_supportive_never_a_fabricated_wealth_yoga():
    result = assess_business_category_suitability(
        "banking", strongest_planet_code=None, house_verdict_bucket={},
        yogas=[{"key": "mahapurusha_sa"}], business_start_decision=None,
    )
    assert result["supportive_yoga_present"] is False
    result = assess_business_category_suitability(
        "banking", strongest_planet_code=None, house_verdict_bucket={},
        yogas=[{"key": "gajakesari"}], business_start_decision=None,
    )
    assert result["supportive_yoga_present"] is True
