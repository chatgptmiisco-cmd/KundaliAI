from app.astro.charts import house_number
from app.astro.yogas import (
    compute_panch_mahapurusha_yogas,
    has_conservative_raj_yoga,
    has_gajakesari_yoga,
)


def test_gajakesari_yoga_present_when_jupiter_in_kendra_from_moon():
    # Jupiter in Cancer(3), Moon in Aries(0) -> house_number(3,0) = 4 -> Kendra.
    assert has_gajakesari_yoga(house_number(3, 0)) is True


def test_gajakesari_yoga_absent_outside_kendra():
    # Jupiter in Taurus(1), Moon in Aries(0) -> house 2 -> not Kendra.
    assert has_gajakesari_yoga(house_number(1, 0)) is False


def test_panch_mahapurusha_yoga_detects_own_sign_in_kendra():
    # Mars (Ruchaka) in its own sign, house 1 from Lagna (Kendra).
    planet_house_from_lagna = {"Ma": 1, "Me": 3, "Ju": 5, "Ve": 6, "Sa": 8}
    planet_dignity = {"Ma": "own_sign", "Me": "neutral", "Ju": "neutral", "Ve": "neutral", "Sa": "neutral"}
    yogas = compute_panch_mahapurusha_yogas(planet_house_from_lagna, planet_dignity)
    assert len(yogas) == 1
    assert yogas[0].planet == "Ma"
    assert yogas[0].name == "Ruchaka"


def test_panch_mahapurusha_yoga_requires_both_dignity_and_kendra():
    # Mars exalted but NOT in a Kendra house -> no yoga.
    planet_house_from_lagna = {"Ma": 3, "Me": 3, "Ju": 5, "Ve": 6, "Sa": 8}
    planet_dignity = {"Ma": "exalted", "Me": "neutral", "Ju": "neutral", "Ve": "neutral", "Sa": "neutral"}
    assert compute_panch_mahapurusha_yogas(planet_house_from_lagna, planet_dignity) == []


def test_conservative_raj_yoga_detects_kendra_trikona_conjunction():
    # Lagna Aries(0): house_lords via classical rulership —
    # house1=Ma(own), house4=Mo, house5=Su, house7=Ve, house9=Ju, house10=Sa.
    house_lords = {1: "Ma", 4: "Mo", 5: "Su", 7: "Ve", 9: "Ju", 10: "Sa"}
    # Kendra lord Saturn (house10) and Trikona lord Jupiter (house9) both sit in house 3.
    planet_house = {"Ma": 1, "Mo": 6, "Su": 2, "Ve": 7, "Ju": 3, "Sa": 3}
    assert has_conservative_raj_yoga(house_lords, planet_house) is True


def test_conservative_raj_yoga_absent_when_no_shared_house():
    house_lords = {1: "Ma", 4: "Mo", 5: "Su", 7: "Ve", 9: "Ju", 10: "Sa"}
    planet_house = {"Ma": 1, "Mo": 6, "Su": 2, "Ve": 7, "Ju": 3, "Sa": 9}
    assert has_conservative_raj_yoga(house_lords, planet_house) is False
