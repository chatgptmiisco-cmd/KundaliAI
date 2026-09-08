"""Transit snapshots: where each planet currently sits, and which natal
(whole-sign) house that activates relative to a birth chart's Lagna and Moon.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.astro.charts import house_number, sign_index
from app.astro.constants import PlanetKey
from app.astro.ephemeris import all_planet_positions, julian_day_ut


@dataclass(frozen=True)
class TransitSnapshot:
    at: datetime
    planet_sign_index: dict[PlanetKey, int]
    planet_house_from_lagna: dict[PlanetKey, int]
    planet_house_from_moon: dict[PlanetKey, int]
    planet_retrograde: dict[PlanetKey, bool]


def compute_transit_snapshot(at_utc: datetime, lagna_sign_index: int, moon_sign_index: int) -> TransitSnapshot:
    jd = julian_day_ut(at_utc)
    positions = all_planet_positions(jd)

    planet_sign: dict[PlanetKey, int] = {}
    house_from_lagna: dict[PlanetKey, int] = {}
    house_from_moon: dict[PlanetKey, int] = {}
    retrograde: dict[PlanetKey, bool] = {}

    for planet, pos in positions.items():
        s = sign_index(pos.longitude)
        planet_sign[planet] = s
        house_from_lagna[planet] = house_number(s, lagna_sign_index)
        house_from_moon[planet] = house_number(s, moon_sign_index)
        retrograde[planet] = pos.speed < 0

    return TransitSnapshot(
        at=at_utc,
        planet_sign_index=planet_sign,
        planet_house_from_lagna=house_from_lagna,
        planet_house_from_moon=house_from_moon,
        planet_retrograde=retrograde,
    )


def daily_snapshots(start: date, end: date, lagna_sign_index: int, moon_sign_index: int) -> list[TransitSnapshot]:
    """One snapshot per day at 12:00 UTC — coarse enough for astrology
    (sign-level transit activity), cheap enough to compute for a year range
    without touching an ephemeris data file."""
    snapshots = []
    current = start
    while current <= end:
        at = datetime(current.year, current.month, current.day, 12, 0, tzinfo=timezone.utc)
        snapshots.append(compute_transit_snapshot(at, lagna_sign_index, moon_sign_index))
        current += timedelta(days=1)
    return snapshots
