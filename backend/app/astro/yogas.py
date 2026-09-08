"""Classical planetary-combination (yoga) detection: a deliberately small,
classically-unambiguous starter set (Gajakesari, Panch Mahapurusha, and one
conservative Raj Yoga indicator), same convention as app.astro.doshas — a
clear, honest starting scope rather than every yoga in the texts.
"""
from dataclasses import dataclass

from app.astro.constants import PlanetKey

_KENDRA_HOUSES = {1, 4, 7, 10}
_TRIKONA_HOUSES = {1, 5, 9}

_MAHAPURUSHA_PLANET_NAMES: dict[PlanetKey, str] = {
    "Ma": "Ruchaka", "Me": "Bhadra", "Ju": "Hamsa", "Ve": "Malavya", "Sa": "Sasa",
}


def has_gajakesari_yoga(house_number_moon_to_jupiter: int) -> bool:
    """Moon and Jupiter in mutual Kendra — pass Jupiter's whole-sign house
    counted from the Moon (i.e. app.astro.charts.house_number(jupiter_sign,
    moon_sign))."""
    return house_number_moon_to_jupiter in _KENDRA_HOUSES


@dataclass(frozen=True)
class MahapurushaYoga:
    planet: PlanetKey
    name: str


def compute_panch_mahapurusha_yogas(
    planet_house_from_lagna: dict[PlanetKey, int],
    planet_dignity: dict[PlanetKey, str],
) -> list[MahapurushaYoga]:
    """Ruchaka/Bhadra/Hamsa/Malavya/Sasa: Mars/Mercury/Jupiter/Venus/Saturn
    exalted or in its own sign, AND placed in a Kendra (1/4/7/10) from Lagna."""
    yogas = []
    for planet, name in _MAHAPURUSHA_PLANET_NAMES.items():
        if (
            planet_house_from_lagna.get(planet) in _KENDRA_HOUSES
            and planet_dignity.get(planet) in ("exalted", "own_sign")
        ):
            yogas.append(MahapurushaYoga(planet=planet, name=name))
    return yogas


def has_conservative_raj_yoga(house_lords: dict[int, PlanetKey], planet_house: dict[PlanetKey, int]) -> bool:
    """A Kendra-lord and a (different) Trikona-lord occupying the same house
    — one narrow, classically uncontroversial Raj Yoga pattern, not the full
    catalog of Raj Yoga combinations."""
    for kendra_house in _KENDRA_HOUSES:
        kendra_lord = house_lords.get(kendra_house)
        if kendra_lord is None:
            continue
        for trikona_house in _TRIKONA_HOUSES:
            trikona_lord = house_lords.get(trikona_house)
            if trikona_lord is None or trikona_lord == kendra_lord:
                continue
            if planet_house.get(kendra_lord) == planet_house.get(trikona_lord):
                return True
    return False
