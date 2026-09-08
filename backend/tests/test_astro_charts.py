"""Unit tests for divisional chart math.

Since there's no internet access here to cross-check against a live
reference calculator, these tests instead verify the closed-form functions
against the classical rule stated in plain words (modality-based for
Navamsa, odd/even-based for Dashamsa) computed independently, for every one
of the 12 signs — if the closed form ever drifts from the classical rule for
any sign, one of these fails.
"""
import pytest

from app.astro.charts import (
    dashamsa_sign_index,
    degree_in_sign,
    house_number,
    navamsa_sign_index,
    sign_index,
)
from app.astro.constants import SIGN_MODALITY

MOVABLE, FIXED, DUAL = 0, 1, 2


def classical_navamsa_start(rasi: int) -> int:
    modality = SIGN_MODALITY[rasi]
    if modality == MOVABLE:
        return rasi
    if modality == FIXED:
        return (rasi + 8) % 12  # 9th sign from itself, inclusive counting
    return (rasi + 4) % 12  # dual: 5th sign from itself, inclusive counting


def classical_dashamsa_start(rasi: int) -> int:
    is_odd_sign = rasi % 2 == 0  # rasi 0=Aries is the 1st sign, i.e. odd
    if is_odd_sign:
        return rasi
    return (rasi + 8) % 12  # 9th sign from itself


@pytest.mark.parametrize("rasi", range(12))
@pytest.mark.parametrize("pada", range(9))
def test_navamsa_matches_classical_modality_rule(rasi, pada):
    longitude = rasi * 30 + pada * (30 / 9) + 0.1  # +0.1 to stay clear of the boundary
    expected = (classical_navamsa_start(rasi) + pada) % 12
    assert navamsa_sign_index(longitude) == expected


@pytest.mark.parametrize("rasi", range(12))
@pytest.mark.parametrize("part", range(10))
def test_dashamsa_matches_classical_odd_even_rule(rasi, part):
    longitude = rasi * 30 + part * 3 + 0.1
    expected = (classical_dashamsa_start(rasi) + part) % 12
    assert dashamsa_sign_index(longitude) == expected


def test_sign_index_boundaries():
    assert sign_index(0) == 0
    assert sign_index(29.999) == 0
    assert sign_index(30) == 1
    assert sign_index(359.999) == 11
    assert sign_index(360) == 0  # wraps


def test_degree_in_sign():
    assert degree_in_sign(45) == 15
    assert degree_in_sign(0) == 0
    assert degree_in_sign(390) == 0  # 390 = 13*30 exactly


def test_house_number_whole_sign():
    # Lagna in Aries(0): house 1 = Aries, house 7 = Libra(6)
    assert house_number(0, lagna_sign_idx=0) == 1
    assert house_number(6, lagna_sign_idx=0) == 7
    # Lagna in Taurus(1): house 1 = Taurus, house 12 = Aries(0)
    assert house_number(1, lagna_sign_idx=1) == 1
    assert house_number(0, lagna_sign_idx=1) == 12
    # wrap-around: Lagna in Pisces(11), house 2 = Aries(0)
    assert house_number(0, lagna_sign_idx=11) == 2
