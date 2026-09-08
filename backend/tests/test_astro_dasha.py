from datetime import datetime, timezone

import pytest

from app.astro.constants import (
    VIMSHOTTARI_SEQUENCE,
    VIMSHOTTARI_YEARS,
    nakshatra_lord,
)
from app.astro.dasha import (
    compute_mahadashas,
    compute_pratyantardashas,
    find_current_antardasha,
    find_current_mahadasha,
    nakshatra_index_and_fraction,
)

BIRTH = datetime(1990, 1, 25, 6, 30, tzinfo=timezone.utc)


def test_nakshatra_lord_cycle_known_assignments():
    # Well-known classical assignments, spot-checked.
    assert nakshatra_lord(0) == "Ke"  # Ashwini
    assert nakshatra_lord(1) == "Ve"  # Bharani
    assert nakshatra_lord(2) == "Su"  # Krittika
    assert nakshatra_lord(8) == "Me"  # Ashlesha (end of first 9-cycle)
    assert nakshatra_lord(9) == "Ke"  # Magha (cycle repeats)
    assert nakshatra_lord(26) == "Me"  # Revati


def test_nakshatra_index_and_fraction_at_boundary():
    idx, frac = nakshatra_index_and_fraction(0.0)
    assert idx == 0
    assert frac == 0.0

    span = 360 / 27
    idx, frac = nakshatra_index_and_fraction(span * 3 + span / 2)
    assert idx == 3
    assert frac == pytest.approx(0.5)


def test_first_mahadasha_is_full_when_moon_at_nakshatra_start():
    mahadashas = compute_mahadashas(BIRTH, moon_sidereal_longitude=0.0)
    first = mahadashas[0]
    assert first.lord == nakshatra_lord(0)
    expected_years = VIMSHOTTARI_YEARS[first.lord]
    actual_years = (first.end - first.start).days / 365.2425
    assert abs(actual_years - expected_years) < 0.01


def test_first_mahadasha_balance_shrinks_as_moon_advances_through_nakshatra():
    span = 360 / 27
    early = compute_mahadashas(BIRTH, moon_sidereal_longitude=0.01)[0]
    late = compute_mahadashas(BIRTH, moon_sidereal_longitude=span * 0.9)[0]
    early_years = (early.end - early.start).days
    late_years = (late.end - late.start).days
    assert late_years < early_years


def test_mahadasha_sequence_follows_vimshottari_order_after_first():
    mahadashas = compute_mahadashas(BIRTH, moon_sidereal_longitude=5.0, cycles=1)
    lords = [m.lord for m in mahadashas]
    # After the first (truncated) lord, the rest must follow the fixed cycle
    # order starting right after it.
    first_lord = lords[0]
    start = VIMSHOTTARI_SEQUENCE.index(first_lord)
    expected_rest = (VIMSHOTTARI_SEQUENCE[start:] + VIMSHOTTARI_SEQUENCE[:start])[1:9]
    assert lords[1:9] == expected_rest


def test_antardashas_sum_to_mahadasha_duration():
    mahadashas = compute_mahadashas(BIRTH, moon_sidereal_longitude=45.0)
    for m in mahadashas[:3]:
        total = sum((a.end - a.start).total_seconds() for a in m.antardashas)
        expected = (m.end - m.start).total_seconds()
        assert abs(total - expected) < 1.0  # within 1 second of rounding
        assert m.antardashas[0].lord == m.lord  # antardasha sequence starts at mahadasha lord
        assert len(m.antardashas) == 9


def test_pratyantardashas_sum_to_antardasha_duration():
    mahadashas = compute_mahadashas(BIRTH, moon_sidereal_longitude=45.0)
    antardasha = mahadashas[0].antardashas[0]
    sub_periods = compute_pratyantardashas(antardasha)
    total = sum((s.end - s.start).total_seconds() for s in sub_periods)
    expected = (antardasha.end - antardasha.start).total_seconds()
    assert abs(total - expected) < 1.0
    assert sub_periods[0].lord == antardasha.lord
    assert len(sub_periods) == 9


def test_find_current_mahadasha_and_antardasha():
    mahadashas = compute_mahadashas(BIRTH, moon_sidereal_longitude=45.0)
    probe = mahadashas[2].start
    current = find_current_mahadasha(mahadashas, probe)
    assert current is mahadashas[2]
    current_antardasha = find_current_antardasha(current, probe)
    assert current_antardasha is current.antardashas[0]
