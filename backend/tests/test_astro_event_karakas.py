from app.astro.event_karakas import CATEGORY_KARAKAS, karaka_specificity_multiplier


def test_jupiter_and_venus_are_shared_and_get_discounted():
    # Jupiter: marriage, wealth, children, foreign_travel (4 categories).
    # Venus: marriage, wealth (2 categories).
    assert karaka_specificity_multiplier("Ju") < 1.0
    assert karaka_specificity_multiplier("Ve") < 1.0


def test_single_category_karakas_are_not_discounted():
    # Saturn/Sun are career-only; Rahu is foreign_travel-only.
    assert karaka_specificity_multiplier("Sa") == 1.0
    assert karaka_specificity_multiplier("Su") == 1.0
    assert karaka_specificity_multiplier("Ra") == 1.0


def test_a_planet_that_is_no_ones_karaka_is_not_discounted():
    assert karaka_specificity_multiplier("Mo") == 1.0
    assert karaka_specificity_multiplier("Ke") == 1.0


def test_category_karakas_registry_matches_the_five_event_categories():
    assert set(CATEGORY_KARAKAS) == {"marriage", "career", "wealth", "children", "foreign_travel"}
