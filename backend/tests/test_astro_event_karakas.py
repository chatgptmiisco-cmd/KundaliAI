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
    assert set(CATEGORY_KARAKAS) == {
        "marriage", "career", "wealth", "children", "foreign_travel",
        # Phase 2 sub-intents — career_promotion/business_expansion are
        # aliases of career's/wealth's own karaka sets (see
        # event_karakas.py's own comment on why they're added AFTER
        # _KARAKA_CATEGORY_COUNT is computed); business_partnership is a
        # genuinely new domain (Mercury).
        "career_promotion", "business_partnership", "business_expansion",
    }


def test_career_promotion_and_business_expansion_do_not_inflate_specificity_counts():
    # Regression guard for a real bug caught before shipping: registering
    # career_promotion/business_expansion as their own CATEGORY_KARAKAS
    # entries (reusing career's/wealth's karakas) must NOT change whether
    # Sa/Su/Ju/Ve count as "shared across categories" for the ALREADY-
    # shipped career/wealth categories — that would silently start
    # discounting their existing karaka rules purely because a new
    # sub-intent was added.
    assert karaka_specificity_multiplier("Sa") == 1.0  # career's exclusive karaka, unaffected
    assert karaka_specificity_multiplier("Su") == 1.0  # ditto
    assert karaka_specificity_multiplier("Me") == 1.0  # business_partnership's own karaka, not shared
    assert CATEGORY_KARAKAS["career_promotion"] == CATEGORY_KARAKAS["career"]
    assert CATEGORY_KARAKAS["business_expansion"] == CATEGORY_KARAKAS["wealth"]
