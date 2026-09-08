from app.astro.doshas import (
    compute_kaal_sarp_dosha,
    compute_kemadruma_dosha,
    compute_sade_sati,
)


def test_kaal_sarp_present_when_all_planets_on_one_side_of_rahu_ketu():
    # Rahu in Aries(0), Ketu in Libra(6). All 7 classical planets in Taurus(1)
    # through Virgo(5) -> houses 2-6 from Rahu -> Kaal Sarp present.
    planet_sign_index = {"Su": 1, "Mo": 2, "Ma": 3, "Me": 4, "Ju": 5, "Ve": 1, "Sa": 2}
    facts = compute_kaal_sarp_dosha(
        lagna_sign_index=0, rahu_sign_index=0, ketu_sign_index=6, planet_sign_index=planet_sign_index,
    )
    assert facts.is_present is True
    assert facts.rahu_house == 1
    assert facts.ketu_house == 7


def test_kaal_sarp_absent_when_planets_straddle_the_axis():
    # Sun in Taurus(1, house 2 from Rahu) but Jupiter in Scorpio(7, house 8
    # from Rahu) -> planets on both sides -> not present.
    planet_sign_index = {"Su": 1, "Mo": 2, "Ma": 3, "Me": 4, "Ju": 7, "Ve": 1, "Sa": 2}
    facts = compute_kaal_sarp_dosha(
        lagna_sign_index=0, rahu_sign_index=0, ketu_sign_index=6, planet_sign_index=planet_sign_index,
    )
    assert facts.is_present is False


def test_sade_sati_phases_by_saturn_house_from_natal_moon():
    # Natal Moon in Capricorn(9). Saturn transiting Sagittarius(8) = house 12 from Moon -> rising.
    assert compute_sade_sati(natal_moon_sign_index=9, transiting_saturn_sign_index=8).phase == "rising"
    # Saturn transiting Capricorn(9) = house 1 from Moon -> peak.
    assert compute_sade_sati(natal_moon_sign_index=9, transiting_saturn_sign_index=9).phase == "peak"
    # Saturn transiting Aquarius(10) = house 2 from Moon -> setting.
    assert compute_sade_sati(natal_moon_sign_index=9, transiting_saturn_sign_index=10).phase == "setting"
    # Saturn transiting Aries(0) = house 4 from Moon -> not active.
    inactive = compute_sade_sati(natal_moon_sign_index=9, transiting_saturn_sign_index=0)
    assert inactive.is_active is False
    assert inactive.phase is None


def test_kemadruma_present_with_no_supporting_or_cancelling_placements():
    # No planet in house 2, 12 (adjacent) or 1/4/7/10 (Kendra) from Moon.
    planet_house_from_moon = {"Su": 3, "Ma": 5, "Me": 6, "Ju": 8, "Ve": 9, "Sa": 11}
    assert compute_kemadruma_dosha(planet_house_from_moon).is_present is True


def test_kemadruma_cancelled_by_kendra_placement():
    planet_house_from_moon = {"Su": 3, "Ma": 4, "Me": 6, "Ju": 8, "Ve": 9, "Sa": 11}
    assert compute_kemadruma_dosha(planet_house_from_moon).is_present is False


def test_kemadruma_absent_when_adjacent_house_occupied():
    planet_house_from_moon = {"Su": 2, "Ma": 5, "Me": 6, "Ju": 8, "Ve": 9, "Sa": 11}
    assert compute_kemadruma_dosha(planet_house_from_moon).is_present is False
