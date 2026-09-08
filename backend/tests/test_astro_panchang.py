from datetime import date

from app.astro.panchang import (
    LUNAR_MONTH_NAMES_EN,
    WEEKDAY_COLOR_EN,
    compute_tithi,
    festival_today,
    is_makar_sankranti,
    lunar_month_index,
    lunar_month_name,
    nakshatra_pada,
    tithi_name,
    weekday_lord,
)


def test_compute_tithi_shukla_paksha_groups():
    # 15 degrees ahead of the Sun -> tithi index 2 (Dwitiya), Shukla paksha
    tithi = compute_tithi(sun_longitude=0.0, moon_longitude=15.0)
    assert tithi.index == 2
    assert tithi.paksha == "shukla"
    assert tithi.number_in_paksha == 2
    assert tithi.group == "bhadra"
    assert tithi.energy_tag == "consolidate"


def test_compute_tithi_krishna_paksha_wraps_number_in_paksha():
    # 190 degrees ahead -> index 16 -> first tithi of Krishna paksha
    tithi = compute_tithi(sun_longitude=10.0, moon_longitude=200.0)
    assert tithi.index == 16
    assert tithi.paksha == "krishna"
    assert tithi.number_in_paksha == 1
    assert tithi.group == "nanda"
    assert tithi.energy_tag == "start"


def test_compute_tithi_purna_group_on_full_and_new_moon():
    # 175 degrees ahead -> still within tithi 15 (Purnima, the 168-180 span) -> Purna group
    full_moon = compute_tithi(sun_longitude=0.0, moon_longitude=175.0)
    assert full_moon.index == 15
    assert full_moon.group == "purna"
    assert full_moon.energy_tag == "finish"

    # Exactly 0 degrees apart (new moon) -> index 1 -> Nanda group
    new_moon = compute_tithi(sun_longitude=50.0, moon_longitude=50.0)
    assert new_moon.index == 1
    assert new_moon.group == "nanda"


def test_nakshatra_pada_quarters_are_hand_verifiable():
    # Nakshatra span is 13.3333..deg, so each pada is ~3.3333deg wide.
    assert nakshatra_pada(1.0) == 1
    assert nakshatra_pada(5.0) == 2
    assert nakshatra_pada(15.0) == 1  # 15 % 13.333 = 1.667deg into the 2nd nakshatra -> its pada 1
    assert nakshatra_pada(12.0) == 4


def test_weekday_lord_matches_classical_table():
    assert weekday_lord(date(2024, 1, 1)) == "Mo"  # Monday
    assert weekday_lord(date(2024, 1, 2)) == "Ma"  # Tuesday
    assert weekday_lord(date(2024, 1, 7)) == "Su"  # Sunday


def test_weekday_color_table_covers_all_seven_planets():
    assert set(WEEKDAY_COLOR_EN) == {"Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa"}


def test_tithi_name_covers_ordinary_tithis_and_the_15th_special_case():
    ordinary = compute_tithi(sun_longitude=0.0, moon_longitude=15.0)  # Dwitiya
    assert tithi_name(ordinary, "en") == "Dwitiya"
    assert tithi_name(ordinary, "hi") == "द्वितीया"

    full_moon = compute_tithi(sun_longitude=0.0, moon_longitude=175.0)  # 15th, Shukla
    assert tithi_name(full_moon, "en") == "Purnima"
    assert tithi_name(full_moon, "hi") == "पूर्णिमा"

    new_moon = compute_tithi(sun_longitude=0.0, moon_longitude=355.0)  # 15th, Krishna
    assert new_moon.paksha == "krishna"
    assert new_moon.number_in_paksha == 15
    assert tithi_name(new_moon, "en") == "Amavasya"
    assert tithi_name(new_moon, "hi") == "अमावस्या"


def test_lunar_month_index_matches_the_amanta_solar_sign_correspondence():
    # Sun in Aries (0-30 deg) -> Vaishakha; Sun in Pisces (330-360 deg) -> Chaitra.
    assert lunar_month_index(15.0) == 0
    assert lunar_month_name(15.0, "en") == "Vaishakha"
    assert lunar_month_index(345.0) == 11
    assert lunar_month_name(345.0, "en") == "Chaitra"
    assert len(LUNAR_MONTH_NAMES_EN) == 12


def test_festival_today_finds_diwali_on_kartika_krishna_amavasya():
    # Kartika = month index 6. Krishna Amavasya = 15th tithi of Krishna paksha.
    amavasya = compute_tithi(sun_longitude=0.0, moon_longitude=355.0)
    assert amavasya.paksha == "krishna" and amavasya.number_in_paksha == 15
    assert festival_today(6, amavasya, "en") == "Diwali (Amavasya)"
    assert festival_today(6, amavasya, "hi") == "दिवाली (अमावस्या)"


def test_festival_today_returns_none_on_an_ordinary_day():
    ordinary = compute_tithi(sun_longitude=0.0, moon_longitude=40.0)
    assert festival_today(2, ordinary, "en") is None


def test_is_makar_sankranti_detects_the_capricorn_ingress_day():
    # Yesterday still in Sagittarius (sign 8, <270deg), today just crossed into Capricorn (sign 9).
    assert is_makar_sankranti(sun_longitude_today=270.5, sun_longitude_yesterday=269.5) is True
    assert is_makar_sankranti(sun_longitude_today=275.0, sun_longitude_yesterday=274.0) is False
    assert is_makar_sankranti(sun_longitude_today=269.9, sun_longitude_yesterday=268.9) is False
