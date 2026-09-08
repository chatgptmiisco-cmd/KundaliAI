"""D1 (Rasi), D9 (Navamsa) and D10 (Dashamsa) chart computation.

All three divisional charts reduce to the same question for every longitude:
which of the 12 signs does this division fall into? D1 is trivial (just the
sign the longitude sits in). D9 and D10 subdivide each 30° sign into 9 or 10
equal parts and place those parts across the zodiac starting from a
sign-dependent point — see the docstrings on each function below for the
classical rule and a worked verification.

House numbers are whole-sign: house N = the sign N positions after the
Lagna's sign, wrapping at 12.
"""
from dataclasses import dataclass
from typing import Literal

from app.astro.constants import PlanetKey, SIGN_MODALITY
from app.astro.ephemeris import all_planet_positions, ascendant_sidereal

ChartType = Literal["D1", "D9", "D10"]


def sign_index(longitude: float) -> int:
    """0 = Aries .. 11 = Pisces."""
    return int(longitude % 360 // 30)


def degree_in_sign(longitude: float) -> float:
    return longitude % 30


def house_number(sign_idx: int, lagna_sign_idx: int) -> int:
    """Whole-sign house number (1-12) for a placement in `sign_idx`, given
    the Lagna sits in `lagna_sign_idx`."""
    return (sign_idx - lagna_sign_idx) % 12 + 1


def navamsa_sign_index(longitude: float) -> int:
    """D9. Each 30° sign splits into 9 padas of 3°20'.

    Classical rule: movable signs start their navamsa count from themselves,
    fixed signs from the 9th sign from themselves, dual signs from the 5th.
    That rule is exactly equivalent to the closed-form
        sign = (rasi * 9 + pada) % 12
    (verified by hand for all 12 signs against the modality rule above —
    see tests/test_astro_charts.py::test_navamsa_matches_classical_modality_rule).
    """
    rasi = sign_index(longitude)
    pada = int(degree_in_sign(longitude) // (30 / 9))
    return (rasi * 9 + pada) % 12


def dashamsa_sign_index(longitude: float) -> int:
    """D10. Each 30° sign splits into 10 parts of 3°.

    Classical rule: odd signs (Aries, Gemini, Leo, Libra, Sagittarius,
    Aquarius) start their dashamsa count from themselves; even signs (Taurus,
    Cancer, Virgo, Scorpio, Capricorn, Pisces) start from the 9th sign from
    themselves. Unlike Navamsa this does NOT reduce to a simple (rasi*10+part)
    formula, so the odd/even branch is explicit here.
    """
    rasi = sign_index(longitude)
    part = int(degree_in_sign(longitude) // 3)
    starting_sign = rasi if rasi % 2 == 0 else (rasi + 8) % 12
    return (starting_sign + part) % 12


def _divisional_sign(longitude: float, division: ChartType) -> int:
    if division == "D1":
        return sign_index(longitude)
    if division == "D9":
        return navamsa_sign_index(longitude)
    return dashamsa_sign_index(longitude)


@dataclass(frozen=True)
class ChartResult:
    chart_type: ChartType
    lagna_sign_index: int
    lagna_longitude: float  # real sidereal longitude, degrees [0, 360) — the D1 Lagna, regardless of division
    planet_sign_index: dict[PlanetKey, int]
    planet_house: dict[PlanetKey, int]
    planet_retrograde: dict[PlanetKey, bool]
    # Real sidereal longitude per planet, degrees [0, 360) — always the D1
    # (raw) longitude even on a D9/D10 result, since "Grah Spashta" (exact
    # degree/nakshatra/pada) is inherently a D1 concept: a divisional chart's
    # sign is a computed bucket, not a position with its own independent degree.
    planet_longitude: dict[PlanetKey, float]


def compute_chart(jd_ut: float, latitude: float, longitude: float, division: ChartType) -> ChartResult:
    lagna_longitude = ascendant_sidereal(jd_ut, latitude, longitude)
    lagna_sign = _divisional_sign(lagna_longitude, division)

    positions = all_planet_positions(jd_ut)
    planet_sign: dict[PlanetKey, int] = {}
    planet_house: dict[PlanetKey, int] = {}
    planet_retrograde: dict[PlanetKey, bool] = {}
    planet_longitude: dict[PlanetKey, float] = {}

    for planet, pos in positions.items():
        s = _divisional_sign(pos.longitude, division)
        planet_sign[planet] = s
        planet_house[planet] = house_number(s, lagna_sign)
        # Retrograde status is always read off the D1 (real) motion, even for
        # divisional charts — a planet doesn't "go retrograde" differently
        # per varga.
        planet_retrograde[planet] = pos.speed < 0
        planet_longitude[planet] = pos.longitude

    return ChartResult(
        chart_type=division,
        lagna_sign_index=lagna_sign,
        lagna_longitude=lagna_longitude,
        planet_sign_index=planet_sign,
        planet_house=planet_house,
        planet_retrograde=planet_retrograde,
        planet_longitude=planet_longitude,
    )
