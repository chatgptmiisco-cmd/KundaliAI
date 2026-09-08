from app.astro.manglik import compute_manglik_facts


def test_manglik_true_when_mars_in_seventh_house_from_lagna():
    facts = compute_manglik_facts(mars_sign_index=6, mars_house_from_lagna=7, moon_sign_index=3)
    assert facts.is_manglik is True
    assert facts.mars_house_from_lagna == 7


def test_manglik_false_when_mars_outside_dosha_houses():
    facts = compute_manglik_facts(mars_sign_index=6, mars_house_from_lagna=5, moon_sign_index=3)
    assert facts.is_manglik is False


def test_manglik_checks_all_six_dosha_houses():
    for house in (1, 2, 4, 7, 8, 12):
        facts = compute_manglik_facts(mars_sign_index=0, mars_house_from_lagna=house, moon_sign_index=0)
        assert facts.is_manglik is True, f"house {house} should be a dosha house"
    for house in (3, 5, 6, 9, 10, 11):
        facts = compute_manglik_facts(mars_sign_index=0, mars_house_from_lagna=house, moon_sign_index=0)
        assert facts.is_manglik is False, f"house {house} should not be a dosha house"


def test_mars_in_own_sign_detected():
    aries = compute_manglik_facts(mars_sign_index=0, mars_house_from_lagna=1, moon_sign_index=0)
    scorpio = compute_manglik_facts(mars_sign_index=7, mars_house_from_lagna=1, moon_sign_index=0)
    taurus = compute_manglik_facts(mars_sign_index=1, mars_house_from_lagna=1, moon_sign_index=0)
    assert aries.mars_in_own_sign is True
    assert scorpio.mars_in_own_sign is True
    assert taurus.mars_in_own_sign is False


def test_mars_house_from_moon_uses_moon_as_reference():
    # Mars in sign 6 (Libra); Moon in sign 3 (Cancer) → house = (6-3)%12+1 = 4
    facts = compute_manglik_facts(mars_sign_index=6, mars_house_from_lagna=1, moon_sign_index=3)
    assert facts.mars_house_from_moon == 4
