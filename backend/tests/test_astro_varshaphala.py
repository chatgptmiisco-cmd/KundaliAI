from datetime import datetime, timezone

import pytest

from app.astro.charts import sign_index
from app.astro.ephemeris import julian_day_ut, planet_position
from app.astro.varshaphala import (
    compute_muntha,
    compute_solar_return,
    compute_varsha_lagna,
    compute_varshaphala,
    varsheshwar,
)

BIRTH = datetime(1990, 1, 25, 6, 30, tzinfo=timezone.utc)
BIRTH_LAT, BIRTH_LON = 28.6, 77.2  # New Delhi

_NATAL_SUN_LONGITUDE = planet_position(julian_day_ut(BIRTH), "Su").longitude


def test_solar_return_lands_near_the_birthday_anniversary():
    target_year = 2030
    solar_return = compute_solar_return(BIRTH, _NATAL_SUN_LONGITUDE, target_year)

    anniversary = BIRTH.replace(year=target_year)
    assert abs((solar_return - anniversary).total_seconds()) < 2 * 24 * 3600  # within ~2 days


def test_solar_return_actually_matches_natal_sun_longitude():
    solar_return = compute_solar_return(BIRTH, _NATAL_SUN_LONGITUDE, 2030)
    jd = julian_day_ut(solar_return)
    returned_longitude = planet_position(jd, "Su").longitude
    diff = abs((returned_longitude - _NATAL_SUN_LONGITUDE + 180) % 360 - 180)
    assert diff < 0.01  # sub-hundredth-of-a-degree precision


def test_solar_return_is_deterministic_and_year_specific():
    a = compute_solar_return(BIRTH, _NATAL_SUN_LONGITUDE, 2030)
    b = compute_solar_return(BIRTH, _NATAL_SUN_LONGITUDE, 2030)
    c = compute_solar_return(BIRTH, _NATAL_SUN_LONGITUDE, 2031)
    assert a == b
    assert a.year == 2030
    assert c.year == 2031
    assert c > a


def test_varsha_lagna_is_a_valid_sign_index():
    solar_return = compute_solar_return(BIRTH, _NATAL_SUN_LONGITUDE, 2030)
    varsha_lagna = compute_varsha_lagna(solar_return, BIRTH_LAT, BIRTH_LON)
    assert 0 <= varsha_lagna <= 11


def test_varsheshwar_matches_known_sign_lords():
    assert varsheshwar(0) == "Ma"  # Aries
    assert varsheshwar(3) == "Mo"  # Cancer
    assert varsheshwar(6) == "Ve"  # Libra


def test_muntha_progresses_one_house_per_completed_year():
    natal_lagna = 4  # Leo
    assert compute_muntha(natal_lagna, 0) == 4  # birth year: Muntha = Lagna itself
    assert compute_muntha(natal_lagna, 1) == 5  # 1st birthday: 2nd house from Lagna
    assert compute_muntha(natal_lagna, 12) == 4  # full 12-house cycle returns to Lagna


def test_compute_varshaphala_differs_across_two_different_charts():
    natal_lagna_a = sign_index(10.0)  # Aries lagna
    natal_lagna_b = sign_index(200.0)  # Libra lagna
    other_birth = datetime(1985, 6, 10, 14, 15, tzinfo=timezone.utc)
    other_sun_longitude = planet_position(julian_day_ut(other_birth), "Su").longitude

    result_a = compute_varshaphala(BIRTH, _NATAL_SUN_LONGITUDE, natal_lagna_a, BIRTH_LAT, BIRTH_LON, 2030)
    result_b = compute_varshaphala(other_birth, other_sun_longitude, natal_lagna_b, BIRTH_LAT, BIRTH_LON, 2030)

    # Two structurally different charts should not collapse to the same Muntha.
    assert result_a.muntha_sign_index != result_b.muntha_sign_index
    assert result_a.solar_return_dt.date() != result_b.solar_return_dt.date()
