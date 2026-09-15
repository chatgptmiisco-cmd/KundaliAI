"""Thin, well-tested wrapper around pyswisseph (Swiss Ephemeris).

Uses the built-in Moshier semi-analytic ephemeris (FLG_MOSEPH) rather than
the full JPL/Swiss data files — no external ephemeris files to download or
ship, and it's accurate to a fraction of an arcsecond for any date in the
1800-2200 range, which is more than sufficient for astrology (nakshatra
boundaries are 13°20' wide; sign boundaries are 30° wide).

This module is synchronous per call — callers running inside async request
handlers should offload calls here to a thread (`anyio.to_thread.run_sync`)
since the underlying C calls block.

IMPORTANT: `swe.set_sid_mode()` sets sidereal-mode state that is NOT shared
across threads in the underlying C library — a worker thread that never
calls it falls back to swisseph's default ayanamsa (Fagan-Bradley, ~0.88°
away from Lahiri for the present era), silently producing a wrong-but-
plausible-looking chart with every value off by a near-constant amount.
Every function below that touches sidereal state therefore calls
`_ensure_lahiri_sidereal_mode()` itself, right before the calculation,
rather than relying on the one-time call some other thread made — this is
correct (and cheap: it's a trivial state set) regardless of which thread
`anyio.to_thread.run_sync` happens to schedule it on.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

import swisseph as swe

from app.astro.constants import PlanetKey


def _ensure_lahiri_sidereal_mode() -> None:
    swe.set_sid_mode(swe.SIDM_LAHIRI)


_CALC_FLAGS = swe.FLG_MOSEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

_BODY_CODES: dict[PlanetKey, int] = {
    "Su": swe.SUN,
    "Mo": swe.MOON,
    "Ma": swe.MARS,
    "Me": swe.MERCURY,
    "Ju": swe.JUPITER,
    "Ve": swe.VENUS,
    "Sa": swe.SATURN,
    # Ra/Ke handled specially below (Ketu = Rahu + 180°)
}


@dataclass(frozen=True)
class PlanetPosition:
    longitude: float  # sidereal ecliptic longitude, degrees [0, 360)
    speed: float  # degrees/day; negative = retrograde


def julian_day_ut(dt_utc: datetime) -> float:
    """dt_utc must be a UTC datetime (naive datetimes are assumed already UTC)."""
    if dt_utc.tzinfo is not None:
        dt_utc = dt_utc.astimezone(timezone.utc)
    hour = dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour)


def calendar_date_utc(jd_ut: float) -> datetime:
    """Inverse of julian_day_ut, truncated to whole seconds — Shadbala's
    Hora/Vara Bala (app.astro.shadbala) need the plain UTC calendar date of
    a computed sunrise moment (to read off its weekday), not another
    ephemeris quantity."""
    year, month, day, hour = swe.revjul(jd_ut)
    whole_hour = int(hour)
    minute_float = (hour - whole_hour) * 60
    minute = int(minute_float)
    second = round((minute_float - minute) * 60)
    return datetime(year, month, day, whole_hour, minute, second, tzinfo=timezone.utc)


def get_ayanamsa(jd_ut: float) -> float:
    _ensure_lahiri_sidereal_mode()
    return swe.get_ayanamsa_ut(jd_ut)


def declination(jd_ut: float, planet: PlanetKey) -> float:
    """Equatorial declination (degrees, positive = north of the celestial
    equator) — Shadbala's Ayana Bala (app.astro.shadbala) needs this, not
    ecliptic longitude, since "how far a planet has strayed toward/away from
    the celestial equator" is a genuinely different axis than sign position.
    Uses Swiss Ephemeris's own equatorial-coordinate transform rather than
    hand-deriving declination from ecliptic longitude/latitude — same
    "thin wrapper, not a reimplementation" convention as the rest of this
    module. Tropical, not sidereal (declination is measured from the real
    celestial equator regardless of which ayanamsa is in use, so sidereal
    mode is irrelevant here — this is the one calculation in this module
    that does NOT call _ensure_lahiri_sidereal_mode)."""
    if planet == "Ke":
        return -declination(jd_ut, "Ra")  # exactly opposite the Moon's node
    body = swe.MEAN_NODE if planet == "Ra" else _BODY_CODES[planet]
    pos, _ = swe.calc_ut(jd_ut, body, swe.FLG_MOSEPH | swe.FLG_EQUATORIAL)
    return pos[1]


def sunrise_utc(jd_ut_approx: float, latitude: float, longitude: float) -> float:
    """Julian Day (UT) of the sunrise nearest at-or-after `jd_ut_approx`, at
    the given geographic position — Shadbala's day/night-dependent limbs
    (app.astro.shadbala's Kaala Bala) need this for Nathonnata/Tribhaga/Hora
    Bala. Uses Swiss Ephemeris's own rise/transit solver (accounts for
    atmospheric refraction and the Sun's apparent radius by default) rather
    than a hand-rolled solar-altitude formula."""
    _res, times = swe.rise_trans(jd_ut_approx, swe.SUN, swe.CALC_RISE, (longitude, latitude, 0), flags=swe.FLG_MOSEPH)
    return times[0]


def sunset_utc(jd_ut_approx: float, latitude: float, longitude: float) -> float:
    """Julian Day (UT) of the sunset nearest at-or-after `jd_ut_approx` — see
    sunrise_utc."""
    _res, times = swe.rise_trans(jd_ut_approx, swe.SUN, swe.CALC_SET, (longitude, latitude, 0), flags=swe.FLG_MOSEPH)
    return times[0]


def planet_position(jd_ut: float, planet: PlanetKey) -> PlanetPosition:
    _ensure_lahiri_sidereal_mode()
    if planet == "Ra":
        pos, _ = swe.calc_ut(jd_ut, swe.MEAN_NODE, _CALC_FLAGS)
        return PlanetPosition(longitude=pos[0] % 360, speed=pos[3])
    if planet == "Ke":
        rahu = planet_position(jd_ut, "Ra")
        return PlanetPosition(longitude=(rahu.longitude + 180) % 360, speed=rahu.speed)

    pos, _ = swe.calc_ut(jd_ut, _BODY_CODES[planet], _CALC_FLAGS)
    return PlanetPosition(longitude=pos[0] % 360, speed=pos[3])


def all_planet_positions(jd_ut: float) -> dict[PlanetKey, PlanetPosition]:
    keys: list[PlanetKey] = ["Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Ra", "Ke"]
    return {k: planet_position(jd_ut, k) for k in keys}


def ascendant_sidereal(jd_ut: float, latitude: float, longitude: float) -> float:
    """Sidereal longitude of the Ascendant (Lagna), degrees [0, 360)."""
    _ensure_lahiri_sidereal_mode()
    _cusps, ascmc = swe.houses_ex(jd_ut, latitude, longitude, b"W", flags=swe.FLG_SIDEREAL)
    return ascmc[0] % 360
