from datetime import datetime, timezone

import pytest

from app.astro.shadbala import (
    MINIMUM_RUPAS,
    ShadbalaChartInputs,
    _enclosing_day_and_night,
    _WEEKDAY_LORDS,
    _weekday_of_sunrise,
    ayana_bala,
    cheshta_bala,
    compound_relation,
    compute_all_shadbala,
    compute_time_of_day_facts,
    day_night_window,
    dig_bala,
    drekkana_bala,
    drik_bala,
    hora_bala,
    hora_lord_at,
    kendradi_bala,
    naisargika_bala,
    nathonnata_bala,
    ojhayugmarasyamsa_bala,
    paksha_bala,
    saptavargaja_bala,
    temporary_relation,
    tribhaga_bala,
    uccha_bala,
    vara_bala,
)


# --- Naisargika Bala ---------------------------------------------------------

def test_naisargika_bala_matches_the_classical_rank_order_and_endpoints():
    assert naisargika_bala("Su") == 60.0
    assert naisargika_bala("Sa") == pytest.approx(60.0 / 7.0)
    assert naisargika_bala("Su") > naisargika_bala("Mo") > naisargika_bala("Ve")
    assert naisargika_bala("Ve") > naisargika_bala("Ju") > naisargika_bala("Me")
    assert naisargika_bala("Me") > naisargika_bala("Ma") > naisargika_bala("Sa")


def test_naisargika_bala_sums_to_the_published_total_of_240():
    total = sum(naisargika_bala(p) for p in ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa"))
    assert total == pytest.approx(240.0)


# --- Uccha Bala ---------------------------------------------------------------

def test_uccha_bala_is_maximum_at_exact_exaltation_and_zero_at_exact_debilitation():
    assert uccha_bala("Su", 10.0) == pytest.approx(60.0)  # 10 deg Aries
    assert uccha_bala("Su", 190.0) == pytest.approx(0.0)  # 10 deg Libra


def test_uccha_bala_is_the_classical_midpoint_ninety_degrees_from_exaltation():
    assert uccha_bala("Su", 100.0) == pytest.approx(30.0)


# --- Kendradi Bala -------------------------------------------------------------

@pytest.mark.parametrize("house,expected", [(1, 60.0), (4, 60.0), (7, 60.0), (10, 60.0)])
def test_kendradi_bala_kendra_houses(house, expected):
    assert kendradi_bala(house) == expected


@pytest.mark.parametrize("house,expected", [(2, 30.0), (5, 30.0), (8, 30.0), (11, 30.0)])
def test_kendradi_bala_panapara_houses(house, expected):
    assert kendradi_bala(house) == expected


@pytest.mark.parametrize("house", [3, 6, 9, 12])
def test_kendradi_bala_apoklima_houses(house):
    assert kendradi_bala(house) == 15.0


# --- Ojhayugmarasyamsa Bala -----------------------------------------------------

def test_ojhayugmarasyamsa_bala_female_planet_wants_even_signs():
    assert ojhayugmarasyamsa_bala("Mo", d1_sign=1, d9_sign=1) == 30.0  # Taurus (even) in both
    assert ojhayugmarasyamsa_bala("Mo", d1_sign=0, d9_sign=1) == 15.0  # Aries (odd) in D1 only


def test_ojhayugmarasyamsa_bala_male_and_neutral_planets_want_odd_signs():
    assert ojhayugmarasyamsa_bala("Su", d1_sign=0, d9_sign=0) == 30.0  # Aries (odd) in both
    assert ojhayugmarasyamsa_bala("Sa", d1_sign=0, d9_sign=0) == 30.0


# --- Drekkana Bala ---------------------------------------------------------------

def test_drekkana_bala_male_planet_matches_first_decan():
    assert drekkana_bala("Su", longitude=5.0) == 15.0
    assert drekkana_bala("Su", longitude=15.0) == 0.0


def test_drekkana_bala_neutral_planet_matches_second_decan():
    assert drekkana_bala("Sa", longitude=15.0) == 15.0
    assert drekkana_bala("Sa", longitude=5.0) == 0.0


def test_drekkana_bala_female_planet_matches_third_decan():
    assert drekkana_bala("Ve", longitude=25.0) == 15.0
    assert drekkana_bala("Ve", longitude=5.0) == 0.0


# --- Panchadha Maitri + Saptavargaja Bala ----------------------------------------

def test_temporary_relation_matches_the_classical_house_groups():
    for house in (2, 3, 4, 10, 11, 12):
        assert temporary_relation(house) == "friend"
    for house in (1, 5, 6, 7, 8, 9):
        assert temporary_relation(house) == "enemy"


def test_compound_relation_combines_natural_and_temporary_scores():
    # Sun and Moon are natural friends; same sign (house 1) is a temporary enemy -> neutral.
    assert compound_relation("Su", "Mo", other_sign_from_planet_sign=1) == "neutral"
    # Sun and Moon, house 2 from each other -> temporary friend too -> great friend.
    assert compound_relation("Su", "Mo", other_sign_from_planet_sign=2) == "great_friend"
    # Sun and Venus are natural enemies; same sign is also a temporary enemy -> great enemy.
    assert compound_relation("Su", "Ve", other_sign_from_planet_sign=1) == "great_enemy"


def test_saptavargaja_bala_scores_moolatrikona_higher_than_plain_own_sign_in_d1_only():
    natal = {"Su": 4, "Mo": 4, "Ma": 4, "Me": 4, "Ju": 4, "Ve": 4, "Sa": 4}
    varga_signs = {"D2": 4, "D3": 4, "D7": 4, "D9": 4, "D12": 4, "D30": 4}
    at_moolatrikona = saptavargaja_bala("Su", 4, 10.0, varga_signs, natal)  # Leo, 10 deg (within 0-20)
    outside_moolatrikona = saptavargaja_bala("Su", 4, 25.0, varga_signs, natal)  # Leo, 25 deg
    assert at_moolatrikona == pytest.approx(45.0 + 30.0 * 6)  # D1 moolatrikona + 6x own
    assert outside_moolatrikona == pytest.approx(30.0 * 7)  # own sign everywhere


def test_saptavargaja_bala_uses_compound_relation_when_planet_does_not_own_the_varga_sign():
    # Sun in a varga sign it neither owns nor moolatrikonas: score should
    # equal the compound-relation points to that sign's lord.
    natal = {"Su": 3, "Mo": 3, "Ma": 3, "Me": 3, "Ju": 3, "Ve": 3, "Sa": 3}  # all in Cancer (Moon's sign)
    varga_signs = {"D2": 4, "D3": 4, "D7": 4, "D9": 4, "D12": 4, "D30": 4}  # irrelevant here
    score = saptavargaja_bala("Su", 3, 15.0, {}, natal)  # only D1, sign=Cancer (lord Moon)
    relation = compound_relation("Su", "Mo", other_sign_from_planet_sign=1)  # same sign as Sun
    from app.astro.shadbala import _SAPTAVARGAJA_POINTS
    assert score == pytest.approx(_SAPTAVARGAJA_POINTS[relation])


# --- Dig Bala -------------------------------------------------------------------

def test_dig_bala_is_maximum_at_the_strong_cusp_and_zero_at_the_weak_cusp():
    lagna = 0.0  # Aries rising
    # Jupiter is strong at the 1st cusp (Lagna itself) and weak at the 7th.
    assert dig_bala("Ju", longitude=0.0, lagna_longitude=lagna) == pytest.approx(60.0)
    assert dig_bala("Ju", longitude=180.0, lagna_longitude=lagna) == pytest.approx(0.0)


def test_dig_bala_sun_and_mars_share_the_tenth_house_strong_point():
    lagna = 0.0
    tenth_cusp = 270.0
    assert dig_bala("Su", tenth_cusp, lagna) == pytest.approx(60.0)
    assert dig_bala("Ma", tenth_cusp, lagna) == pytest.approx(60.0)


# --- Paksha Bala ------------------------------------------------------------------

def test_paksha_bala_favors_benefics_at_full_moon_and_malefics_at_new_moon():
    assert paksha_bala(sun_longitude=0.0, moon_longitude=180.0, planet="Ju") == pytest.approx(60.0)
    assert paksha_bala(sun_longitude=0.0, moon_longitude=180.0, planet="Sa") == pytest.approx(0.0)
    assert paksha_bala(sun_longitude=0.0, moon_longitude=0.0, planet="Ju") == pytest.approx(0.0)
    assert paksha_bala(sun_longitude=0.0, moon_longitude=0.0, planet="Sa") == pytest.approx(60.0)


def test_paksha_bala_moon_is_doubled():
    assert paksha_bala(sun_longitude=0.0, moon_longitude=180.0, planet="Mo") == pytest.approx(120.0)


# --- Ayana Bala -------------------------------------------------------------------

def test_ayana_bala_is_at_its_base_maximum_for_full_northern_declination():
    # Venus (northern-favoring): declination = obliquity -> base formula maxes at 60.
    assert ayana_bala("Ve", 23.45) == pytest.approx(60.0, abs=0.5)


def test_ayana_bala_moon_and_saturn_favor_southern_declination():
    assert ayana_bala("Sa", -23.45) == pytest.approx(60.0, abs=0.5)
    assert ayana_bala("Sa", 23.45) == pytest.approx(0.0, abs=0.5)


def test_ayana_bala_mercury_benefits_from_either_direction():
    north = ayana_bala("Me", 23.45)
    south = ayana_bala("Me", -23.45)
    assert north == pytest.approx(south)
    assert north == pytest.approx(60.0, abs=0.5)


def test_ayana_bala_sun_is_doubled():
    # Sun follows the same "northern favors" rule as Venus/Mars/Jupiter, then doubles.
    assert ayana_bala("Su", 23.45) == pytest.approx(120.0, abs=1.0)


# --- Day/night window + Hora/Vara Bala ---------------------------------------------

_DELHI = (28.6139, 77.2090)


def test_day_night_window_correctly_flips_across_a_sunset_boundary():
    from app.astro.ephemeris import julian_day_ut

    midday = julian_day_ut(datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc))
    evening = julian_day_ut(datetime(2024, 6, 15, 14, 5, tzinfo=timezone.utc))  # just after Delhi sunset
    assert day_night_window(midday, *_DELHI).is_day is True
    assert day_night_window(evening, *_DELHI).is_day is False


def test_enclosing_day_and_night_always_orders_day_before_night():
    from app.astro.ephemeris import julian_day_ut

    for hour in (2, 10, 14, 20):
        jd = julian_day_ut(datetime(2024, 6, 15, hour, 0, tzinfo=timezone.utc))
        window = day_night_window(jd, *_DELHI)
        day_w, night_w = _enclosing_day_and_night(window, *_DELHI)
        assert day_w.is_day is True
        assert night_w.is_day is False
        assert day_w.end == pytest.approx(night_w.start)


def test_nathonnata_bala_mercury_is_always_sixty():
    from app.astro.ephemeris import julian_day_ut

    jd = julian_day_ut(datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc))
    window = day_night_window(jd, *_DELHI)
    assert nathonnata_bala("Me", jd, window) == 60.0


def test_nathonnata_bala_diurnal_planet_scores_zero_during_the_unfavorable_window():
    from app.astro.ephemeris import julian_day_ut

    jd = julian_day_ut(datetime(2024, 6, 15, 14, 5, tzinfo=timezone.utc))  # night
    window = day_night_window(jd, *_DELHI)
    assert nathonnata_bala("Su", jd, window) == 0.0


def test_tribhaga_bala_jupiter_is_always_sixty():
    from app.astro.ephemeris import julian_day_ut

    jd = julian_day_ut(datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc))
    window = day_night_window(jd, *_DELHI)
    assert tribhaga_bala("Ju", jd, window) == 60.0


def test_tribhaga_bala_exactly_one_non_jupiter_planet_scores_in_a_given_third():
    from app.astro.ephemeris import julian_day_ut

    jd = julian_day_ut(datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc))
    window = day_night_window(jd, *_DELHI)
    scores = {p: tribhaga_bala(p, jd, window) for p in ("Su", "Mo", "Ma", "Me", "Ve", "Sa")}
    assert sum(1 for v in scores.values() if v == 60.0) == 1


def test_vara_bala_only_the_weekday_lord_scores():
    scores = {p: vara_bala(p, weekday_lord="Sa") for p in ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa")}
    assert scores["Sa"] == 45.0
    assert sum(1 for v in scores.values() if v > 0) == 1


def test_hora_bala_only_the_hora_lord_scores():
    scores = {p: hora_bala(p, current_hora_lord="Ma") for p in ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa")}
    assert scores["Ma"] == 60.0
    assert sum(1 for v in scores.values() if v > 0) == 1


def test_hora_lord_at_cycles_through_the_full_chaldean_sequence_across_a_day():
    from app.astro.ephemeris import julian_day_ut

    day_start_jd = julian_day_ut(datetime(2024, 6, 15, 0, 0, tzinfo=timezone.utc))
    window = day_night_window(day_start_jd, *_DELHI)
    day_w, _night_w = _enclosing_day_and_night(window, *_DELHI)
    lords_seen = set()
    for i in range(12):
        sample_jd = day_w.start + (day_w.end - day_w.start) * (i + 0.5) / 12
        lords_seen.add(hora_lord_at(sample_jd, *_DELHI))
    assert len(lords_seen) == 7  # all 7 planets appear across 12 Horas (5 repeat once)


# --- Cheshta Bala -------------------------------------------------------------------

def test_cheshta_bala_sun_and_moon_reuse_ayana_and_paksha():
    assert cheshta_bala("Su", speed=1.0, sun_ayana_bala=42.0, moon_paksha_bala=99.0) == 42.0
    assert cheshta_bala("Mo", speed=13.0, sun_ayana_bala=42.0, moon_paksha_bala=99.0) == 99.0


def test_cheshta_bala_retrograde_is_always_maximum():
    assert cheshta_bala("Ma", speed=-0.1, sun_ayana_bala=0, moon_paksha_bala=0) == 60.0


def test_cheshta_bala_at_exact_mean_speed_is_the_classical_minimum():
    assert cheshta_bala("Ma", speed=0.524, sun_ayana_bala=0, moon_paksha_bala=0) == pytest.approx(30.0)


def test_cheshta_bala_increases_away_from_the_mean_speed_in_either_direction():
    at_mean = cheshta_bala("Ma", speed=0.524, sun_ayana_bala=0, moon_paksha_bala=0)
    slower = cheshta_bala("Ma", speed=0.2, sun_ayana_bala=0, moon_paksha_bala=0)
    faster = cheshta_bala("Ma", speed=1.0, sun_ayana_bala=0, moon_paksha_bala=0)
    assert slower > at_mean
    assert faster > at_mean


# --- Drik Bala ----------------------------------------------------------------------

def test_drik_bala_is_zero_when_multiplier_is_neutral():
    assert drik_bala(1.0) == 0.0


def test_drik_bala_is_positive_for_a_benefic_leaning_multiplier_and_negative_for_afflicted():
    assert drik_bala(1.5) == pytest.approx(60.0)
    assert drik_bala(0.5) == pytest.approx(-60.0)  # clamped from -60


# --- Full integration ----------------------------------------------------------------

def _build_test_chart_inputs() -> ShadbalaChartInputs:
    from app.astro.charts import house_number, navamsa_sign_index, sign_index
    from app.astro.ephemeris import all_planet_positions, ascendant_sidereal, declination, julian_day_ut
    from app.astro.natal_insights import aspect_and_conjunction_multiplier
    from app.astro.vargas import (
        drekkana_sign_index,
        dwadashamsa_sign_index,
        hora_sign_index,
        saptamsa_sign_index,
        trimshamsa_sign_index,
    )

    birth = datetime(1990, 1, 25, 6, 30, tzinfo=timezone.utc)
    lat, lon = 28.6, 77.2
    jd = julian_day_ut(birth)
    positions = all_planet_positions(jd)
    lagna_longitude = ascendant_sidereal(jd, lat, lon)
    lagna_sign = sign_index(lagna_longitude)
    planets = ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa")

    natal_sign = {p: sign_index(positions[p].longitude) for p in planets}
    natal_house = {p: house_number(natal_sign[p], lagna_sign) for p in planets}
    natal_longitude = {p: positions[p].longitude for p in planets}
    birth_window, weekday_lord, current_hora_lord = compute_time_of_day_facts(jd, lat, lon)

    return ShadbalaChartInputs(
        natal_planet_sign=natal_sign,
        natal_planet_longitude=natal_longitude,
        natal_planet_speed={p: positions[p].speed for p in planets},
        natal_planet_house=natal_house,
        natal_planet_d9_sign={p: navamsa_sign_index(positions[p].longitude) for p in planets},
        natal_planet_varga_signs={
            p: {
                "D2": hora_sign_index(positions[p].longitude),
                "D3": drekkana_sign_index(positions[p].longitude),
                "D7": saptamsa_sign_index(positions[p].longitude),
                "D12": dwadashamsa_sign_index(positions[p].longitude),
                "D30": trimshamsa_sign_index(positions[p].longitude),
            }
            for p in planets
        },
        natal_planet_declination={p: declination(jd, p) for p in planets},
        natal_planet_aspect_multiplier={
            p: aspect_and_conjunction_multiplier(p, natal_house[p], natal_house) for p in planets
        },
        lagna_longitude=lagna_longitude,
        birth_jd_ut=jd,
        latitude=lat,
        longitude=lon,
        birth_window=birth_window,
        weekday_lord=weekday_lord,
        current_hora_lord=current_hora_lord,
    )


def test_compute_all_shadbala_covers_all_seven_classical_planets_with_sane_totals():
    chart = _build_test_chart_inputs()
    results = compute_all_shadbala(chart)
    assert set(results) == {"Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa"}
    for planet, result in results.items():
        assert result.planet == planet
        assert result.minimum_rupas == MINIMUM_RUPAS[planet]
        assert result.is_strong == (result.total_rupas >= result.minimum_rupas)
        # A real chart's total should land in a plausible real-world range,
        # not an obviously broken one (e.g. negative, or in the hundreds).
        assert 1.0 < result.total_rupas < 15.0
        assert result.total_virupas == pytest.approx(result.total_rupas * 60.0)


def test_compute_all_shadbala_is_deterministic():
    a = compute_all_shadbala(_build_test_chart_inputs())
    b = compute_all_shadbala(_build_test_chart_inputs())
    assert a == b


def test_compute_time_of_day_facts_matches_computing_each_piece_separately():
    # Regression guard for the redundant-7x-recomputation fix: precomputing
    # once via compute_time_of_day_facts must give EXACTLY the same values
    # as calling day_night_window/hora_lord_at directly — this is a pure
    # extraction for performance, not a behavior change.
    jd, lat, lon = 2451545.0, 28.6, 77.2
    birth_window, weekday_lord, current_hora_lord = compute_time_of_day_facts(jd, lat, lon)
    assert birth_window == day_night_window(jd, lat, lon)
    day_window, _night_window = _enclosing_day_and_night(birth_window, lat, lon)
    assert weekday_lord == _WEEKDAY_LORDS[_weekday_of_sunrise(day_window)]
    assert current_hora_lord == hora_lord_at(jd, lat, lon)


def test_compute_all_shadbala_does_not_recompute_time_of_day_facts_per_planet():
    """Performance regression guard for the exact bug found and fixed this
    session: compute_shadbala used to call day_night_window/hora_lord_at
    (each involving Swiss Ephemeris sunrise/sunset root-finding) once PER
    PLANET instead of once per chart, making ~90% of compute_all_shadbala's
    runtime pure waste. This monkeypatches day_night_window to count calls
    — compute_all_shadbala itself must make ZERO such calls (all 7
    compute_shadbala calls should read birth_window/weekday_lord/
    current_hora_lord off the already-built ShadbalaChartInputs)."""
    import app.astro.shadbala as shadbala_module

    chart = _build_test_chart_inputs()
    call_count = 0
    original = shadbala_module.day_night_window

    def _counting_wrapper(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original(*args, **kwargs)

    shadbala_module.day_night_window = _counting_wrapper
    try:
        compute_all_shadbala(chart)
    finally:
        shadbala_module.day_night_window = original

    assert call_count == 0
