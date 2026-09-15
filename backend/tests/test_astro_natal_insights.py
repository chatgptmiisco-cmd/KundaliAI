import pytest

from app.astro.natal_insights import (
    aspect_and_conjunction_multiplier,
    compute_natal_insights,
    house_lord,
    house_sign,
    planet_dignity,
    shadbala_strength_multiplier,
    significator_strength,
    significator_strength_multipliers,
    sign_lord,
    vargottama_multiplier,
)


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


def test_significator_strength_scales_with_dignity():
    assert significator_strength("exalted", house=1, combust=False) == 1.5
    assert significator_strength("own_sign", house=1, combust=False) == 1.25
    assert significator_strength("neutral", house=1, combust=False) == 1.0
    assert significator_strength("debilitated", house=1, combust=False) == 0.5


def test_significator_strength_stacks_dusthana_and_combustion_penalties():
    # Own-sign in a dusthana house: 1.25 * 0.75 = 0.9375
    assert significator_strength("own_sign", house=8, combust=False) == pytest.approx(0.9375)
    # Own-sign, combust: 1.25 * 0.85 = 1.0625
    assert significator_strength("own_sign", house=1, combust=True) == pytest.approx(1.0625)
    # Debilitated AND dusthana AND combust would fall below the floor unclamped
    # (0.5 * 0.75 * 0.85 = 0.31875) — still above the 0.3 floor here...
    assert significator_strength("debilitated", house=6, combust=True) == pytest.approx(0.31875)


def test_significator_strength_is_clamped_to_a_sane_range():
    # Exalted can never exceed the 1.5 ceiling even with no afflictions to reduce it.
    assert significator_strength("exalted", house=1, combust=False) <= 1.5
    # A deliberately extreme combination would fall under the 0.3 floor unclamped;
    # the floor keeps a "genuinely weak" significator meaningfully weighted rather
    # than effectively erased from the score.
    assert significator_strength("debilitated", house=12, combust=True) >= 0.3


def test_significator_strength_multipliers_computes_one_entry_per_planet():
    planet_sign_index = {"Su": 0, "Mo": 3, "Ma": 7, "Me": 2, "Ju": 8, "Ve": 1, "Sa": 6}
    planet_house = {"Su": 1, "Mo": 4, "Ma": 8, "Me": 3, "Ju": 9, "Ve": 2, "Sa": 7}
    multipliers = significator_strength_multipliers(planet_sign_index, planet_house)

    # Sun exalted in Aries (sign 0), house 1 -> base 1.5, then aspected by
    # BOTH Jupiter (house 9's 5th-house special aspect reaches house 1,
    # benefic *1.1) and Saturn (house 7's universal 7th-house aspect also
    # reaches house 1, malefic *0.9) -> 1.5 * 1.1 * 0.9 = 1.485.
    assert multipliers["Su"] == pytest.approx(1.485)
    # Saturn exalted in Libra (sign 6), house 7 -> base 1.5, aspected only by
    # the Sun's universal 7th-house aspect from house 1 (malefic *0.9) ->
    # 1.5 * 0.9 = 1.35.
    assert multipliers["Sa"] == pytest.approx(1.35)
    # Mars own-sign in Scorpio (sign 7), sitting in dusthana house 8 ->
    # 1.25 * 0.75 = 0.9375, then aspected by Venus's universal 7th-house
    # aspect from house 2 (benefic *1.1) -> 0.9375 * 1.1 = 1.03125.
    assert multipliers["Ma"] == pytest.approx(1.03125)


def test_significator_strength_multipliers_applies_combustion_only_when_longitudes_given():
    planet_sign_index = {"Su": 2, "Mo": 3, "Me": 3}  # Cancer is neutral ground for Mercury
    planet_house = {"Su": 1, "Mo": 4, "Me": 3}

    without_longitude = significator_strength_multipliers(planet_sign_index, planet_house)
    assert without_longitude["Me"] == 1.0  # Mercury neutral here, no combustion check possible

    # Mercury 5 degrees from the Sun -> combust, on top of its neutral dignity.
    planet_longitude = {"Su": 65.0, "Mo": 100.0, "Me": 70.0}
    with_longitude = significator_strength_multipliers(planet_sign_index, planet_house, planet_longitude)
    assert with_longitude["Me"] == pytest.approx(0.85)
    assert with_longitude["Su"] == 1.0  # the Sun itself is never combust


def test_vargottama_multiplier_rewards_the_same_sign_in_d1_and_d9():
    assert vargottama_multiplier(d1_sign=4, d9_sign=4) == 1.15
    assert vargottama_multiplier(d1_sign=4, d9_sign=5) == 1.0


def test_shadbala_strength_multiplier_scales_with_the_rupas_to_minimum_ratio():
    assert shadbala_strength_multiplier(total_rupas=5.0, minimum_rupas=5.0) == pytest.approx(1.0)
    assert shadbala_strength_multiplier(total_rupas=6.5, minimum_rupas=5.0) == pytest.approx(1.3)  # capped
    assert shadbala_strength_multiplier(total_rupas=2.5, minimum_rupas=5.0) == pytest.approx(0.7)  # capped
    assert shadbala_strength_multiplier(total_rupas=5.5, minimum_rupas=5.0) == pytest.approx(1.1)


def test_significator_strength_multipliers_applies_vargottama_when_d9_signs_given():
    planet_sign_index = {"Su": 4}  # Leo, own sign -> base multiplier 1.25
    planet_house = {"Su": 1}
    without_d9 = significator_strength_multipliers(planet_sign_index, planet_house)
    with_vargottama = significator_strength_multipliers(
        planet_sign_index, planet_house, planet_d9_sign_index={"Su": 4}
    )
    with_different_d9 = significator_strength_multipliers(
        planet_sign_index, planet_house, planet_d9_sign_index={"Su": 5}
    )
    assert without_d9["Su"] == pytest.approx(1.25)
    assert with_vargottama["Su"] == pytest.approx(1.25 * 1.15)
    assert with_different_d9["Su"] == pytest.approx(1.25)


def test_significator_strength_multipliers_applies_shadbala_when_results_given():
    class _FakeShadbalaResult:
        def __init__(self, total_rupas, minimum_rupas):
            self.total_rupas = total_rupas
            self.minimum_rupas = minimum_rupas

    planet_sign_index = {"Su": 2}  # neutral dignity -> base multiplier 1.0
    planet_house = {"Su": 1}
    without_shadbala = significator_strength_multipliers(planet_sign_index, planet_house)
    with_strong_shadbala = significator_strength_multipliers(
        planet_sign_index, planet_house,
        shadbala_results={"Su": _FakeShadbalaResult(total_rupas=8.0, minimum_rupas=5.0)},
    )
    assert without_shadbala["Su"] == pytest.approx(1.0)
    assert with_strong_shadbala["Su"] == pytest.approx(1.3)  # capped ratio


def test_aspect_and_conjunction_multiplier_is_neutral_with_no_other_planets_involved():
    assert aspect_and_conjunction_multiplier("Ju", house=1, planet_house={"Ju": 1}) == 1.0


def test_aspect_and_conjunction_multiplier_rewards_a_benefic_aspect():
    # Jupiter in house 9 casts its classical 5th-house special aspect on
    # house 1 (9 + 4 = 13 -> house 1) — a real, distance benefic aspect.
    planet_house = {"Ve": 1, "Ju": 9}
    assert aspect_and_conjunction_multiplier("Ve", house=1, planet_house=planet_house) == pytest.approx(1.1)


def test_aspect_and_conjunction_multiplier_penalizes_a_malefic_aspect():
    # Saturn in house 7 casts its universal 7th-house aspect on house 1.
    planet_house = {"Ve": 1, "Sa": 7}
    assert aspect_and_conjunction_multiplier("Ve", house=1, planet_house=planet_house) == pytest.approx(0.9)


def test_aspect_and_conjunction_multiplier_weighs_conjunction_more_than_aspect():
    # Same benefic (Jupiter), but sharing Venus's own house instead of
    # merely aspecting it from afar — a conjunction is a closer influence
    # and moves the needle further than a distant aspect.
    aspect_only = {"Ve": 1, "Ju": 9}  # Jupiter's 5th-house aspect reaches house 1
    conjunct = {"Ve": 1, "Ju": 1}  # Jupiter sits right there with Venus
    aspect_multiplier = aspect_and_conjunction_multiplier("Ve", house=1, planet_house=aspect_only)
    conjunction_multiplier = aspect_and_conjunction_multiplier("Ve", house=1, planet_house=conjunct)
    assert conjunction_multiplier > aspect_multiplier


def test_aspect_and_conjunction_multiplier_stacks_multiple_influences():
    # Two malefics (Saturn's universal 7th aspect, Mars conjunct) both
    # afflicting the same planet compound rather than the worse one alone
    # deciding it — a real reading treats multiple afflictions as worse than
    # any single one.
    planet_house = {"Ve": 1, "Sa": 7, "Ma": 1}
    multiplier = aspect_and_conjunction_multiplier("Ve", house=1, planet_house=planet_house)
    assert multiplier == pytest.approx(0.9 * 0.85)
