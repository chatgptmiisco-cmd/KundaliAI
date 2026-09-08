from app.astro.natal_insights import compute_natal_insights, house_lord, house_sign, planet_dignity, sign_lord


def test_sign_lord_matches_classical_rulership():
    assert sign_lord(0) == "Ma"  # Aries
    assert sign_lord(3) == "Mo"  # Cancer
    assert sign_lord(4) == "Su"  # Leo
    assert sign_lord(9) == "Sa"  # Capricorn
    assert sign_lord(11) == "Ju"  # Pisces


def test_house_sign_wraps_around_the_zodiac():
    # Lagna in Aquarius (10): house 1 = Aquarius, house 12 = Capricorn, house 3 = Aries (wraps)
    assert house_sign(1, lagna_sign_index=10) == 10
    assert house_sign(12, lagna_sign_index=10) == 9
    assert house_sign(3, lagna_sign_index=10) == 0


def test_house_lord_combines_house_sign_and_rulership():
    # Lagna Aries (0): house 10 = Capricorn (9) -> lord Saturn
    assert house_lord(10, lagna_sign_index=0) == "Sa"
    # Lagna Cancer (3): house 10 = Aries (0) -> lord Mars
    assert house_lord(10, lagna_sign_index=3) == "Ma"


def test_planet_dignity_exalted_debilitated_own_sign_neutral():
    assert planet_dignity("Su", sign_idx=0) == "exalted"  # Sun exalted in Aries
    assert planet_dignity("Su", sign_idx=6) == "debilitated"  # Sun debilitated in Libra
    assert planet_dignity("Su", sign_idx=4) == "own_sign"  # Sun owns Leo
    assert planet_dignity("Su", sign_idx=2) == "neutral"  # Gemini — none of the above
    assert planet_dignity("Sa", sign_idx=0) == "debilitated"  # Saturn debilitated in Aries
    assert planet_dignity("Ma", sign_idx=7) == "own_sign"  # Mars owns Scorpio too


def test_compute_natal_insights_derives_house_lord_placements():
    lagna_sign_index = 0  # Aries
    planet_sign_index = {
        "Su": 2, "Mo": 3, "Ma": 7, "Me": 2, "Ju": 8, "Ve": 1, "Sa": 6,
    }
    planet_house = {
        "Su": 1, "Mo": 4, "Ma": 8, "Me": 3, "Ju": 9, "Ve": 2, "Sa": 7,
    }
    insights = compute_natal_insights(lagna_sign_index, planet_sign_index, planet_house)

    assert insights.lagna_lord == "Ma"  # Aries ruled by Mars
    assert insights.lagna_lord_house == 8  # Mars sits in house 8 here

    # House 10 from Aries = Capricorn -> lord Saturn -> Saturn's house = 7
    assert insights.tenth_lord == "Sa"
    assert insights.tenth_lord_house == 7

    # Saturn sits in Libra (6) here -> exalted
    assert insights.planet_dignity["Sa"] == "exalted"
    assert insights.strongest_planet == "Sa"


def test_compute_natal_insights_finds_debilitated_planet():
    lagna_sign_index = 4  # Leo
    planet_sign_index = {
        "Su": 4, "Mo": 1, "Ma": 8, "Me": 5, "Ju": 6, "Ve": 3, "Sa": 0,  # Saturn in Aries -> debilitated
    }
    planet_house = {
        "Su": 1, "Mo": 6, "Ma": 5, "Me": 2, "Ju": 3, "Ve": 8, "Sa": 9,
    }
    insights = compute_natal_insights(lagna_sign_index, planet_sign_index, planet_house)
    assert insights.weakest_planet == "Sa"
    assert insights.planet_dignity["Sa"] == "debilitated"


def test_compute_natal_insights_generalizes_house_lords_to_all_twelve_houses():
    lagna_sign_index = 0  # Aries
    planet_sign_index = {"Su": 2, "Mo": 3, "Ma": 7, "Me": 2, "Ju": 8, "Ve": 1, "Sa": 6}
    planet_house = {"Su": 1, "Mo": 4, "Ma": 8, "Me": 3, "Ju": 9, "Ve": 2, "Sa": 7}
    insights = compute_natal_insights(lagna_sign_index, planet_sign_index, planet_house)

    assert len(insights.house_lords) == 12
    # House 9 from Aries = Sagittarius -> lord Jupiter -> Jupiter sits in house 9
    assert insights.house_lords[9] == "Ju"
    assert insights.house_lord_houses[9] == 9


def test_blind_spot_flags_lagna_lord_in_dusthana():
    lagna_sign_index = 0  # Aries -> Lagna lord Mars
    planet_sign_index = {"Su": 2, "Mo": 3, "Ma": 7, "Me": 2, "Ju": 8, "Ve": 1, "Sa": 6}
    # Mars placed in house 8 (a dusthana) here.
    planet_house = {"Su": 1, "Mo": 4, "Ma": 8, "Me": 3, "Ju": 9, "Ve": 2, "Sa": 7}
    insights = compute_natal_insights(lagna_sign_index, planet_sign_index, planet_house)

    assert insights.blind_spot_planet == "Ma"
    assert insights.blind_spot_reason == "dusthana_placement"


def test_blind_spot_falls_back_to_weakest_planet_when_lagna_lord_is_clean():
    lagna_sign_index = 4  # Leo -> Lagna lord Sun
    planet_sign_index = {"Su": 4, "Mo": 1, "Ma": 8, "Me": 5, "Ju": 6, "Ve": 3, "Sa": 0}
    planet_house = {"Su": 1, "Mo": 6, "Ma": 5, "Me": 2, "Ju": 3, "Ve": 8, "Sa": 9}
    insights = compute_natal_insights(lagna_sign_index, planet_sign_index, planet_house)

    # Sun sits in house 1 (its own sign, not a dusthana) -> clean lagna lord.
    assert insights.blind_spot_planet == "Sa"
    assert insights.blind_spot_reason == "debilitated"


def test_combustion_detected_only_when_longitudes_supplied():
    lagna_sign_index = 0
    planet_sign_index = {"Su": 2, "Mo": 3, "Ma": 7, "Me": 2, "Ju": 8, "Ve": 1, "Sa": 6}
    planet_house = {"Su": 1, "Mo": 4, "Ma": 8, "Me": 3, "Ju": 9, "Ve": 2, "Sa": 7}

    without_longitude = compute_natal_insights(lagna_sign_index, planet_sign_index, planet_house)
    assert without_longitude.combust_planets == frozenset()

    # Mercury 5 degrees from the Sun -> well within its 14deg combustion orb.
    planet_longitude = {"Su": 65.0, "Mo": 100.0, "Ma": 220.0, "Me": 70.0, "Ju": 250.0, "Ve": 40.0, "Sa": 190.0}
    with_longitude = compute_natal_insights(lagna_sign_index, planet_sign_index, planet_house, planet_longitude)
    assert "Me" in with_longitude.combust_planets
    assert "Ma" not in with_longitude.combust_planets


def test_decision_style_derives_from_lagna_modality():
    lagna_sign_index = 0  # Aries -> movable
    planet_sign_index = {"Su": 2, "Mo": 3, "Ma": 7, "Me": 5, "Ju": 8, "Ve": 1, "Sa": 6}
    planet_house = {"Su": 1, "Mo": 4, "Ma": 8, "Me": 6, "Ju": 9, "Ve": 2, "Sa": 7}
    insights = compute_natal_insights(lagna_sign_index, planet_sign_index, planet_house)
    assert insights.decision_style == "fast_and_decisive"

    # Same Lagna, but Mercury now debilitated (Pisces, index 11) -> decisive tips into impulsive.
    planet_sign_index_debilitated_mercury = {**planet_sign_index, "Me": 11}
    insights_impulsive = compute_natal_insights(
        lagna_sign_index, planet_sign_index_debilitated_mercury, planet_house
    )
    assert insights_impulsive.decision_style == "impulsive_and_reactive"
