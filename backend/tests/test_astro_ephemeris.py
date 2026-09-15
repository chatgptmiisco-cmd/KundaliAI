import threading
from datetime import datetime, timezone

import pytest

from app.astro.charts import compute_chart
from app.astro.ephemeris import (
    ascendant_sidereal,
    declination,
    get_ayanamsa,
    julian_day_ut,
    planet_position,
    sunrise_utc,
    sunset_utc,
)


def test_lahiri_ayanamsa_matches_known_reference_for_j2000():
    # Lahiri ayanamsa on 1 Jan 2000, 12:00 UT is well-documented as ~23°51'
    # (23.85 degrees). Allow a small tolerance for the exact ayanamsa variant.
    jd = julian_day_ut(datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc))
    ayanamsa = get_ayanamsa(jd)
    assert 23.5 < ayanamsa < 24.2


def test_ayanamsa_increases_over_time():
    jd_2000 = julian_day_ut(datetime(2000, 1, 1, tzinfo=timezone.utc))
    jd_2020 = julian_day_ut(datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert get_ayanamsa(jd_2020) > get_ayanamsa(jd_2000)


def test_rahu_ketu_are_always_exactly_opposite():
    jd = julian_day_ut(datetime(1990, 1, 25, 6, 30, tzinfo=timezone.utc))
    rahu = planet_position(jd, "Ra")
    ketu = planet_position(jd, "Ke")
    diff = abs((rahu.longitude - ketu.longitude) % 360)
    assert diff == pytest.approx(180, abs=1e-6)


def test_compute_chart_lagna_is_always_house_one():
    jd = julian_day_ut(datetime(1990, 1, 25, 6, 30, tzinfo=timezone.utc))
    for division in ("D1", "D9", "D10"):
        chart = compute_chart(jd, latitude=28.6, longitude=77.2, division=division)
        # A planet placed in the same sign as the Lagna must be house 1.
        for planet, sign in chart.planet_sign_index.items():
            if sign == chart.lagna_sign_index:
                assert chart.planet_house[planet] == 1


def test_compute_chart_is_deterministic():
    jd = julian_day_ut(datetime(1990, 1, 25, 6, 30, tzinfo=timezone.utc))
    a = compute_chart(jd, 28.6, 77.2, "D1")
    b = compute_chart(jd, 28.6, 77.2, "D1")
    assert a == b


def test_sidereal_calculations_are_correct_from_a_background_thread():
    """Regression test for a real production bug: swisseph's sidereal mode
    (set via swe.set_sid_mode) is NOT shared across threads in the underlying
    C library. Every request-serving call in this app that touches ephemeris
    data runs inside `anyio.to_thread.run_sync`, i.e. on a worker thread that
    never itself called set_sid_mode — before this module made every sidereal
    function call `_ensure_lahiri_sidereal_mode()` itself, every such call
    silently fell back to swisseph's *default* ayanamsa (Fagan-Bradley, ~0.88
    degrees away from Lahiri for the present era), producing a plausible-
    looking but wrong chart for every single API request. This test pins the
    fix by asserting a worker thread gets the exact same numbers as the main
    thread would."""
    jd = julian_day_ut(datetime(2000, 1, 1, 1, 4, tzinfo=timezone.utc))

    main_thread_result: dict = {
        "ayanamsa": get_ayanamsa(jd),
        "sun_longitude": planet_position(jd, "Su").longitude,
        "lagna_longitude": ascendant_sidereal(jd, 27.4924, 77.6737),
    }

    worker_thread_result: dict = {}

    def _worker():
        worker_thread_result["ayanamsa"] = get_ayanamsa(jd)
        worker_thread_result["sun_longitude"] = planet_position(jd, "Su").longitude
        worker_thread_result["lagna_longitude"] = ascendant_sidereal(jd, 27.4924, 77.6737)

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join()

    assert worker_thread_result["ayanamsa"] == pytest.approx(main_thread_result["ayanamsa"], abs=1e-9)
    assert worker_thread_result["sun_longitude"] == pytest.approx(main_thread_result["sun_longitude"], abs=1e-9)
    assert worker_thread_result["lagna_longitude"] == pytest.approx(main_thread_result["lagna_longitude"], abs=1e-9)
    # And it must be the real Lahiri value, not swisseph's Fagan-Bradley default (~24.7 deg here).
    assert 23.5 < worker_thread_result["ayanamsa"] < 24.2


def test_declination_of_the_sun_peaks_near_the_solstices_and_crosses_zero_at_the_equinoxes():
    # Tropical declination (not sidereal) — the Sun's max/min are pinned to
    # the real celestial equator regardless of ayanamsa.
    winter_solstice = julian_day_ut(datetime(2000, 12, 21, 12, tzinfo=timezone.utc))
    summer_solstice = julian_day_ut(datetime(2000, 6, 21, 12, tzinfo=timezone.utc))
    spring_equinox = julian_day_ut(datetime(2000, 3, 20, 12, tzinfo=timezone.utc))

    assert declination(winter_solstice, "Su") == pytest.approx(-23.43, abs=0.1)
    assert declination(summer_solstice, "Su") == pytest.approx(23.43, abs=0.1)
    assert declination(spring_equinox, "Su") == pytest.approx(0.0, abs=0.5)


def test_declination_ketu_is_always_exactly_opposite_rahu():
    jd = julian_day_ut(datetime(1990, 1, 25, 6, 30, tzinfo=timezone.utc))
    assert declination(jd, "Ke") == pytest.approx(-declination(jd, "Ra"), abs=1e-9)


def test_sunrise_and_sunset_searched_from_a_known_local_morning_bracket_the_same_day():
    # Anchor the search at 02:00 UTC = 07:30 IST — solidly after Delhi's real
    # sunrise on this date but well before sunset, so "next sunrise" and
    # "next sunset" from this anchor land on the SAME local day's sunset and
    # the FOLLOWING day's sunrise, in that order. (Anchoring at UTC midnight
    # instead would be misleading here: Delhi's local sunrise, being UTC+5:30,
    # already happened before UTC midnight, so a forward search from midnight
    # finds next sunset today but next sunrise only tomorrow — still correctly
    # ordered, just not "same calendar day" in the way a naive reader expects.)
    anchor = julian_day_ut(datetime(2024, 6, 15, 2, 0, tzinfo=timezone.utc))
    set_ = sunset_utc(anchor, latitude=28.6139, longitude=77.2090)  # Delhi
    next_rise = sunrise_utc(anchor, latitude=28.6139, longitude=77.2090)
    assert anchor < set_ < next_rise
    # A June night in Delhi runs roughly 10-11 hours, not some wildly wrong span.
    assert 0.4 < (next_rise - set_) < 0.48


def test_sunrise_and_sunset_land_on_plausible_local_clock_times_for_a_known_city():
    # Delhi (UTC+5:30), mid-January: sunrise ~07:00-07:30 IST, sunset ~17:30-18:00 IST.
    jd_midnight = julian_day_ut(datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc))
    rise = sunrise_utc(jd_midnight, latitude=28.6139, longitude=77.2090)
    set_ = sunset_utc(jd_midnight, latitude=28.6139, longitude=77.2090)
    rise_ist_hour = ((rise - jd_midnight) * 24 + 5.5) % 24
    set_ist_hour = ((set_ - jd_midnight) * 24 + 5.5) % 24
    assert 6.5 < rise_ist_hour < 7.5
    assert 17.0 < set_ist_hour < 18.5
