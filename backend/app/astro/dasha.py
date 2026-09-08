"""Vimshottari Mahadasha / Antardasha / Pratyantardasha calculation.

Algorithm (classical, per Brihat Parashara Hora Shastra):
  1. Locate the Moon's nakshatra at birth and how far through it the Moon has
     travelled (as a fraction). That fraction determines how much of the
     first Mahadasha's nominal duration has *already elapsed* before birth —
     the remainder ("balance of dasha") is what actually runs from birth.
  2. Subsequent Mahadashas follow the fixed 9-lord Vimshottari sequence, each
     running its full nominal duration, indefinitely cycling.
  3. Each Mahadasha's span is itself divided into 9 Antardashas, proportional
     to each lord's share of the 120-year cycle, in the same 9-lord sequence
     *starting from the Mahadasha's own lord*.
  4. Antardashas subdivide into Pratyantardashas the same way, starting from
     the Antardasha's own lord. These are computed on demand (see
     `compute_pratyantardashas`) rather than eagerly for the whole sequence —
     729 (9x9x9) entries per person is a lot of data nobody asked to see yet.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.astro.constants import (
    DAYS_PER_YEAR,
    NAKSHATRA_SPAN_DEG,
    VIMSHOTTARI_SEQUENCE,
    VIMSHOTTARI_YEARS,
    PlanetKey,
    nakshatra_lord,
)


def _years_to_timedelta(years: float) -> timedelta:
    return timedelta(days=years * DAYS_PER_YEAR)


def _sequence_from(lord: PlanetKey) -> list[PlanetKey]:
    start = VIMSHOTTARI_SEQUENCE.index(lord)
    return VIMSHOTTARI_SEQUENCE[start:] + VIMSHOTTARI_SEQUENCE[:start]


@dataclass(frozen=True)
class SubPeriod:
    lord: PlanetKey
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Antardasha:
    lord: PlanetKey
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Mahadasha:
    lord: PlanetKey
    start: datetime
    end: datetime
    antardashas: list[Antardasha]


def nakshatra_index_and_fraction(moon_sidereal_longitude: float) -> tuple[int, float]:
    longitude = moon_sidereal_longitude % 360
    nak_index = int(longitude // NAKSHATRA_SPAN_DEG)
    degree_in_nak = longitude % NAKSHATRA_SPAN_DEG
    elapsed_fraction = degree_in_nak / NAKSHATRA_SPAN_DEG
    return nak_index, elapsed_fraction


def _antardashas_for(mahadasha_lord: PlanetKey, start: datetime, duration: timedelta) -> list[Antardasha]:
    antardashas = []
    cursor = start
    for lord in _sequence_from(mahadasha_lord):
        share = VIMSHOTTARI_YEARS[lord] / 120
        span = timedelta(seconds=duration.total_seconds() * share)
        end = cursor + span
        antardashas.append(Antardasha(lord=lord, start=cursor, end=end))
        cursor = end
    return antardashas


def compute_pratyantardashas(antardasha: Antardasha) -> list[SubPeriod]:
    duration = antardasha.end - antardasha.start
    sub_periods = []
    cursor = antardasha.start
    for lord in _sequence_from(antardasha.lord):
        share = VIMSHOTTARI_YEARS[lord] / 120
        span = timedelta(seconds=duration.total_seconds() * share)
        end = cursor + span
        sub_periods.append(SubPeriod(lord=lord, start=cursor, end=end))
        cursor = end
    return sub_periods


def compute_mahadashas(birth_dt: datetime, moon_sidereal_longitude: float, cycles: int = 1) -> list[Mahadasha]:
    """Returns the Mahadasha sequence from birth onward: the first entry is
    truncated to its balance-of-dasha, followed by `cycles` full passes
    through the remaining lords (cycles=1 covers one full ~120-year
    Vimshottari span from birth, which is enough for a human lifetime)."""
    nak_index, elapsed_fraction = nakshatra_index_and_fraction(moon_sidereal_longitude)
    first_lord = nakshatra_lord(nak_index)

    mahadashas: list[Mahadasha] = []
    cursor = birth_dt

    balance_years = VIMSHOTTARI_YEARS[first_lord] * (1 - elapsed_fraction)
    duration = _years_to_timedelta(balance_years)
    end = cursor + duration
    mahadashas.append(
        Mahadasha(lord=first_lord, start=cursor, end=end, antardashas=_antardashas_for(first_lord, cursor, duration))
    )
    cursor = end

    sequence_after_first = _sequence_from(first_lord)[1:]
    full_sequence = sequence_after_first
    for _ in range(cycles - 1):
        full_sequence = full_sequence + VIMSHOTTARI_SEQUENCE

    for lord in full_sequence:
        duration = _years_to_timedelta(VIMSHOTTARI_YEARS[lord])
        end = cursor + duration
        mahadashas.append(
            Mahadasha(lord=lord, start=cursor, end=end, antardashas=_antardashas_for(lord, cursor, duration))
        )
        cursor = end

    return mahadashas


def find_current_mahadasha(mahadashas: list[Mahadasha], at: datetime) -> Mahadasha | None:
    for m in mahadashas:
        if m.start <= at < m.end:
            return m
    return None


def find_current_antardasha(mahadasha: Mahadasha, at: datetime) -> Antardasha | None:
    for a in mahadasha.antardashas:
        if a.start <= at < a.end:
            return a
    return None


def find_current_sub_period(sub_periods: list[SubPeriod], at: datetime) -> SubPeriod | None:
    for s in sub_periods:
        if s.start <= at < s.end:
            return s
    return None
