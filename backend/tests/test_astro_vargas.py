import pytest

from app.astro.constants import OWN_SIGNS
from app.astro.vargas import (
    chaturthamsa_sign_index,
    drekkana_sign_index,
    dwadashamsa_sign_index,
    hora_sign_index,
    saptamsa_sign_index,
    trimshamsa_sign_index,
)

_ARIES, _TAURUS, _GEMINI, _CANCER, _LEO, _VIRGO = 0, 1, 2, 3, 4, 5
_LIBRA, _SCORPIO, _SAGITTARIUS, _CAPRICORN, _AQUARIUS, _PISCES = 6, 7, 8, 9, 10, 11


# --- D2 Hora ----------------------------------------------------------------

def test_hora_odd_sign_first_half_is_sun_second_half_is_moon():
    assert hora_sign_index(_ARIES * 30 + 5) == _LEO  # odd sign, 1st half (0-15)
    assert hora_sign_index(_ARIES * 30 + 20) == _CANCER  # odd sign, 2nd half (15-30)


def test_hora_even_sign_first_half_is_moon_second_half_is_sun():
    assert hora_sign_index(_TAURUS * 30 + 5) == _CANCER
    assert hora_sign_index(_TAURUS * 30 + 20) == _LEO


def test_hora_only_ever_returns_cancer_or_leo():
    for sign in range(12):
        for degree in (0.0, 7.5, 14.99, 15.0, 22.5, 29.99):
            assert hora_sign_index(sign * 30 + degree) in (_CANCER, _LEO)


# --- D3 Drekkana --------------------------------------------------------------

def test_drekkana_first_decan_is_the_sign_itself():
    assert drekkana_sign_index(_ARIES * 30 + 3) == _ARIES
    assert drekkana_sign_index(_LIBRA * 30 + 3) == _LIBRA


def test_drekkana_second_decan_is_the_fifth_sign_from_it():
    assert drekkana_sign_index(_ARIES * 30 + 13) == _LEO  # 5th from Aries
    assert drekkana_sign_index(_TAURUS * 30 + 13) == _VIRGO  # 5th from Taurus


def test_drekkana_third_decan_is_the_ninth_sign_from_it():
    assert drekkana_sign_index(_ARIES * 30 + 25) == _SAGITTARIUS  # 9th from Aries
    assert drekkana_sign_index(_CANCER * 30 + 25) == _PISCES  # 9th from Cancer


# --- D7 Saptamsa --------------------------------------------------------------

def test_saptamsa_odd_sign_starts_from_itself():
    span = 30 / 7
    assert saptamsa_sign_index(_ARIES * 30 + 0.1) == _ARIES
    assert saptamsa_sign_index(_ARIES * 30 + span + 0.1) == _TAURUS  # 2nd part


def test_saptamsa_even_sign_starts_from_its_seventh_sign():
    span = 30 / 7
    assert saptamsa_sign_index(_TAURUS * 30 + 0.1) == _SCORPIO  # 7th from Taurus
    assert saptamsa_sign_index(_TAURUS * 30 + span + 0.1) == _SAGITTARIUS


# --- D12 Dwadashamsa ------------------------------------------------------------

def test_dwadashamsa_always_starts_from_the_sign_itself_regardless_of_parity():
    assert dwadashamsa_sign_index(_ARIES * 30 + 0.1) == _ARIES
    assert dwadashamsa_sign_index(_TAURUS * 30 + 0.1) == _TAURUS
    # 2.5 deg per part -> the 5th part (deg 10-12.5) is 4 signs ahead.
    assert dwadashamsa_sign_index(_ARIES * 30 + 11) == _LEO
    assert dwadashamsa_sign_index(_TAURUS * 30 + 11) == _VIRGO


# --- D30 Trimshamsa -------------------------------------------------------------

@pytest.mark.parametrize("rasi", range(12))
def test_trimshamsa_result_is_always_one_of_the_ruling_planets_own_signs(rasi):
    # Independent cross-check against constants.OWN_SIGNS (already verified
    # elsewhere in this codebase) rather than re-deriving expected signs by
    # hand — every Trimshamsa portion's resulting sign must be some
    # classical planet's own sign, by construction of the classical rule.
    all_own_signs = {sign for signs in OWN_SIGNS.values() for sign in signs}
    for degree in (2.0, 7.0, 14.0, 21.0, 27.0):
        result = trimshamsa_sign_index(rasi * 30 + degree)
        assert result in all_own_signs


def test_trimshamsa_odd_sign_boundaries_match_the_classical_degree_ranges():
    # Aries (odd): Mars 0-5, Saturn 5-10, Jupiter 10-18, Mercury 18-25, Venus 25-30.
    assert trimshamsa_sign_index(_ARIES * 30 + 2) == _ARIES  # Mars's odd sign
    assert trimshamsa_sign_index(_ARIES * 30 + 7) == _AQUARIUS  # Saturn's odd sign
    assert trimshamsa_sign_index(_ARIES * 30 + 14) == _SAGITTARIUS  # Jupiter's odd sign
    assert trimshamsa_sign_index(_ARIES * 30 + 21) == _GEMINI  # Mercury's odd sign
    assert trimshamsa_sign_index(_ARIES * 30 + 27) == _LIBRA  # Venus's odd sign


def test_trimshamsa_even_sign_boundaries_match_the_classical_degree_ranges():
    # Taurus (even): Venus 0-5, Mercury 5-12, Jupiter 12-20, Saturn 20-25, Mars 25-30.
    assert trimshamsa_sign_index(_TAURUS * 30 + 2) == _TAURUS  # Venus's even sign
    assert trimshamsa_sign_index(_TAURUS * 30 + 8) == _VIRGO  # Mercury's even sign
    assert trimshamsa_sign_index(_TAURUS * 30 + 15) == _PISCES  # Jupiter's even sign
    assert trimshamsa_sign_index(_TAURUS * 30 + 22) == _CAPRICORN  # Saturn's even sign
    assert trimshamsa_sign_index(_TAURUS * 30 + 27) == _SCORPIO  # Mars's even sign


# --- D4 Chaturthamsa (Phase 9) ------------------------------------------------

def test_chaturthamsa_four_quarters_follow_the_1_4_7_10_kendra_sequence():
    # Aries: 1st quarter (0-7.5) stays Aries, 2nd (7.5-15) -> 4th sign
    # (Cancer), 3rd (15-22.5) -> 7th sign (Libra), 4th (22.5-30) -> 10th
    # sign (Capricorn).
    assert chaturthamsa_sign_index(_ARIES * 30 + 2) == _ARIES
    assert chaturthamsa_sign_index(_ARIES * 30 + 10) == _CANCER
    assert chaturthamsa_sign_index(_ARIES * 30 + 18) == _LIBRA
    assert chaturthamsa_sign_index(_ARIES * 30 + 26) == _CAPRICORN


def test_chaturthamsa_sequence_is_identical_regardless_of_sign_modality():
    # Taurus (fixed) and Gemini (dual) must follow the SAME kendra pattern
    # as Aries (movable) above — the classical rule is explicitly not
    # dependent on chara/sthira/dwiswabhava, unlike D3/D7/D30's odd/even
    # branching.
    assert chaturthamsa_sign_index(_TAURUS * 30 + 2) == _TAURUS
    assert chaturthamsa_sign_index(_TAURUS * 30 + 10) == _LEO
    assert chaturthamsa_sign_index(_TAURUS * 30 + 18) == _SCORPIO
    assert chaturthamsa_sign_index(_TAURUS * 30 + 26) == _AQUARIUS

    assert chaturthamsa_sign_index(_GEMINI * 30 + 2) == _GEMINI
    assert chaturthamsa_sign_index(_GEMINI * 30 + 10) == _VIRGO
    assert chaturthamsa_sign_index(_GEMINI * 30 + 18) == _SAGITTARIUS
    assert chaturthamsa_sign_index(_GEMINI * 30 + 26) == _PISCES


def test_chaturthamsa_quarter_boundaries_are_exactly_7_5_degrees():
    assert chaturthamsa_sign_index(_ARIES * 30 + 7.49) == _ARIES
    assert chaturthamsa_sign_index(_ARIES * 30 + 7.51) == _CANCER
    assert chaturthamsa_sign_index(_ARIES * 30 + 22.49) == _LIBRA
    assert chaturthamsa_sign_index(_ARIES * 30 + 22.51) == _CAPRICORN
