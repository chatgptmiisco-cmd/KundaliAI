"""Varshaphala (Tajika annual chart) — the classical technique behind a real,
computed "how is this year going to be" reading: the exact moment the
transiting Sun returns to its natal degree (the solar return), the Ascendant
at that moment (Varsha Lagna), that Ascendant's ruler (Varsheshwar, the
"year lord"), and the Muntha (the natal Lagna progressed one house per
completed year of age).

Deeper Tajika techniques (Sahams, Ithasala/Isarafa planetary aspects) are a
documented, deliberate omission — this covers the well-established annual-
chart basics every Vedic astrologer uses for a yearly outlook, not the full
Tajika system. See the Prediction Engine plan for why the scope stops here.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.astro.charts import house_number, sign_index
from app.astro.constants import PlanetKey
from app.astro.ephemeris import ascendant_sidereal, julian_day_ut, planet_position
from app.astro.natal_insights import sign_lord


def _angular_diff(a: float, b: float) -> float:
    """a - b, wrapped to (-180, 180] — positive means a is ahead of b along
    the zodiac in the direction of normal (increasing-longitude) motion."""
    return (a - b + 180) % 360 - 180


def compute_solar_return(birth_dt: datetime, natal_sun_longitude: float, target_year: int) -> datetime:
    """The UTC moment in `target_year` when the transiting Sun's sidereal
    longitude exactly matches its longitude at birth — the classical solar
    return, the moment a Varshaphala (annual) chart is cast for.

    The Sun moves ~0.95-1.02 deg/day and never retrogrades, so it crosses any
    target longitude exactly once per year, close to the calendar-date
    anniversary of birth (the two drift apart by roughly a day per year
    against the Gregorian calendar). Bisecting a +/-4 day window around that
    anniversary comfortably covers that drift.
    """
    try:
        anniversary = birth_dt.replace(year=target_year)
    except ValueError:
        # birth_dt is Feb 29 and target_year isn't a leap year.
        anniversary = birth_dt.replace(year=target_year, month=3, day=1)

    def f(dt: datetime) -> float:
        jd = julian_day_ut(dt)
        return _angular_diff(planet_position(jd, "Su").longitude, natal_sun_longitude)

    lo = anniversary - timedelta(days=4)
    hi = anniversary + timedelta(days=4)
    f_lo, f_hi = f(lo), f(hi)
    # f increases monotonically with time; if the calendar-anniversary
    # estimate was unusually far off, widen the bracket once rather than
    # silently returning a wrong root.
    if f_lo > 0:
        lo -= timedelta(days=4)
        f_lo = f(lo)
    if f_hi < 0:
        hi += timedelta(days=4)
        f_hi = f(hi)

    for _ in range(40):  # converges to sub-second precision well within 40 halvings of an 8-16 day window
        mid = lo + (hi - lo) / 2
        f_mid = f(mid)
        if f_mid == 0:
            return mid
        if f_mid < 0:
            lo = mid
        else:
            hi = mid
    return lo + (hi - lo) / 2


def compute_varsha_lagna(solar_return_dt: datetime, latitude: float, longitude: float) -> int:
    """Sign index (0-11) of the Ascendant at the exact solar-return moment —
    the Varsha Lagna, the annual chart's own rising sign (distinct from the
    natal Lagna)."""
    jd = julian_day_ut(solar_return_dt)
    asc_longitude = ascendant_sidereal(jd, latitude, longitude)
    return sign_index(asc_longitude)


def varsheshwar(varsha_lagna_sign_index: int) -> PlanetKey:
    """The Varsha Lagna's ruling planet — the classical "year lord" whose
    general nature colors the whole year."""
    return sign_lord(varsha_lagna_sign_index)


def compute_muntha(natal_lagna_sign_index: int, completed_years: int) -> int:
    """Muntha: the natal Lagna progressed forward one whole sign per
    completed year of age (0 at birth) — a classical Tajika technique for
    tracking which house of the natal chart is "activated" for the year."""
    return (natal_lagna_sign_index + completed_years) % 12


@dataclass(frozen=True)
class VarshaphalaResult:
    solar_return_dt: datetime
    varsha_lagna_sign_index: int
    varsheshwar: PlanetKey
    muntha_sign_index: int
    muntha_house_from_varsha_lagna: int


def compute_varshaphala(
    birth_dt: datetime,
    natal_sun_longitude: float,
    natal_lagna_sign_index: int,
    latitude: float,
    longitude: float,
    target_year: int,
) -> VarshaphalaResult:
    solar_return_dt = compute_solar_return(birth_dt, natal_sun_longitude, target_year)
    varsha_lagna = compute_varsha_lagna(solar_return_dt, latitude, longitude)
    completed_years = target_year - birth_dt.year
    muntha_sign = compute_muntha(natal_lagna_sign_index, completed_years)
    return VarshaphalaResult(
        solar_return_dt=solar_return_dt,
        varsha_lagna_sign_index=varsha_lagna,
        varsheshwar=varsheshwar(varsha_lagna),
        muntha_sign_index=muntha_sign,
        muntha_house_from_varsha_lagna=house_number(muntha_sign, varsha_lagna),
    )
