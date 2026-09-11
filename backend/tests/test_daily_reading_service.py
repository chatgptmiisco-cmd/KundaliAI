"""Unit tests for the pure `_build_reading` assembly function — every input
is hand-constructed (no ephemeris/DB calls), so every expected value below is
derived by hand from the same classical rules the function implements."""
from datetime import date, datetime, timezone

from app.astro.constants import PLANET_NUMBER
from app.astro.natal_insights import compute_natal_insights
from app.astro.panchang import weekday_lord
from app.astro.transits import TransitSnapshot
from app.services.daily_reading_service import _build_reading
from app.services.interpretation.templates import _FOCUS_BY_HOUSE_EN, _LIFE_FRAMING_EN, _PERIOD_CONTENT_EN

_LAGNA_SIGN_INDEX = 0  # Aries
_NATAL_SIGN_INDEX = {"Su": 2, "Mo": 3, "Ma": 7, "Me": 2, "Ju": 8, "Ve": 1, "Sa": 6, "Ra": 0, "Ke": 6}
_NATAL_HOUSE = {"Su": 3, "Mo": 4, "Ma": 8, "Me": 3, "Ju": 9, "Ve": 2, "Sa": 7, "Ra": 1, "Ke": 7}


def _fixture_insights():
    return compute_natal_insights(_LAGNA_SIGN_INDEX, _NATAL_SIGN_INDEX, _NATAL_HOUSE)


def _fake_snapshot(moon_house_from_lagna: int, saturn_sign_index: int) -> TransitSnapshot:
    house_from_lagna = {
        "Su": 5, "Mo": moon_house_from_lagna, "Ma": 9, "Me": 5, "Ju": 2, "Ve": 6, "Sa": 8, "Ra": 3, "Ke": 9,
    }
    sign_index = {"Su": 4, "Mo": 3, "Ma": 8, "Me": 4, "Ju": 1, "Ve": 5, "Sa": saturn_sign_index, "Ra": 2, "Ke": 8}
    return TransitSnapshot(
        at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        planet_sign_index=sign_index,
        planet_house_from_lagna=house_from_lagna,
        planet_house_from_moon=dict(house_from_lagna),
        planet_retrograde={k: False for k in house_from_lagna},
    )


def _base_kwargs(**overrides):
    kwargs = dict(
        for_date=date(2026, 1, 1),
        language="en",
        lagna_sign_index=_LAGNA_SIGN_INDEX,
        moon_sign_index=3,
        rahu_sign_index=0,
        ketu_sign_index=6,
        mars_sign_index=7,
        mars_house_from_lagna=8,
        natal_planet_sign_index=_NATAL_SIGN_INDEX,
        natal_planet_house=_NATAL_HOUSE,
        natal_moon_longitude=100.0,
        insights=_fixture_insights(),
        mahadasha_lord="Ju",
        antardasha_lord="Ve",
        sun_longitude_today=10.0,
        moon_longitude_today=100.0,  # diff=90 -> tithi index 8 -> Jaya group -> "effort"
        sun_longitude_yesterday=9.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_natal_strength_and_blind_spot_are_real_chart_facts():
    reading = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))

    # Saturn is exalted (Libra, sign 6) in this chart -> the chart's real
    # strongest placement, independent of the running Mahadasha (Jupiter).
    assert reading["core_strength"] == _LIFE_FRAMING_EN["Sa"]["core_strength"]
    # Aries' Lagna lord (Mars) sits in house 8 (a dusthana) -> real blind spot.
    assert reading["core_weakness"] == _LIFE_FRAMING_EN["Ma"]["core_challenge"]
    assert reading["stress_pattern"].startswith("Under real pressure, your 6th house")
    assert reading["decision_style"].startswith("You decide fast and commit")


def test_rating_and_energy_mode_shift_with_todays_moon_transit():
    growth_day = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))
    dusthana_day = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(8, saturn_sign_index=4)))

    assert growth_day["dominant_theme"] == _FOCUS_BY_HOUSE_EN[4]
    assert dusthana_day["dominant_theme"] == _FOCUS_BY_HOUSE_EN[8]
    assert growth_day["dominant_theme"] != dusthana_day["dominant_theme"]

    # Moon in a growth house (+1) AND a Jaya tithi (+1) -> antardasha rating boosted by 2.
    assert growth_day["rating"] == _PERIOD_CONTENT_EN["Ve"]["rating"] + 2
    # Moon in a dusthana (-1) still gets the Jaya tithi boost (+1) -> net unchanged from base.
    assert dusthana_day["rating"] == _PERIOD_CONTENT_EN["Ve"]["rating"]

    assert growth_day["energy_mode"] == "creative"  # Venus antardasha, no override
    assert dusthana_day["energy_mode"] == "conflict_prone"  # dusthana transit overrides the lord table


def test_period_rating_and_type_use_the_real_dasha_weighting():
    reading = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))
    ju_rating, ve_rating = _PERIOD_CONTENT_EN["Ju"]["rating"], _PERIOD_CONTENT_EN["Ve"]["rating"]
    expected = round((ju_rating + 2 * ve_rating) / 3)
    assert reading["period_rating"] == expected
    assert reading["mahadasha_label"] == "Jupiter Mahadasha / Venus Antardasha"
    assert reading["period_type"] == "consolidation"


def test_tithi_tag_and_daily_varying_risk_opportunity():
    reading = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))
    assert reading["tithi_tag"] == "effort"  # Jaya group
    risks, opportunities = _PERIOD_CONTENT_EN["Ve"]["risks"], _PERIOD_CONTENT_EN["Ve"]["opportunities"]
    assert reading["key_risk"] == risks[8 % len(risks)]
    assert reading["key_opportunity"] == opportunities[9 % len(opportunities)]


def test_lucky_number_is_the_real_weekday_lords_classical_number():
    reading = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))
    expected_lord = weekday_lord(date(2026, 1, 1))
    assert reading["lucky_number"] == PLANET_NUMBER[expected_lord]


def test_today_guidance_gives_calm_advice_on_a_conflict_prone_dusthana_transit():
    # Moon transiting house 8 (a dusthana house) forces energy_mode to
    # "conflict_prone" regardless of the antardasha lord.
    reading = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(8, saturn_sign_index=4)))
    assert reading["energy_mode"] == "conflict_prone"
    assert len(reading["today_guidance"]) >= 2
    assert "calm" in reading["today_guidance"][0].lower()


def test_today_guidance_reflects_the_real_tithi_energy_tag():
    avoid_starts_reading = _build_reading(
        **_base_kwargs(
            transit_snapshot=_fake_snapshot(4, saturn_sign_index=4),
            sun_longitude_today=10.0,
            moon_longitude_today=50.0,  # diff=40 -> tithi index 4 (Rikta group -> avoid_starts)
        )
    )
    assert avoid_starts_reading["tithi_tag"] == "avoid_starts"
    assert "avoid starting" in avoid_starts_reading["today_guidance"][1].lower()


def test_dosha_summary_reflects_real_placements():
    reading = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))
    doshas = {d["key"]: d for d in reading["doshas"]}
    assert set(doshas) == {"manglik", "kaal_sarp", "sade_sati", "dhaiya", "kemadruma"}
    # Mars sits in house 8 from Lagna (a Manglik house) -> present.
    assert doshas["manglik"]["is_present"] is True
    # All 7 classical planets don't fall entirely on one side of Rahu/Ketu here.
    assert doshas["kaal_sarp"]["is_present"] is False
    # Transiting Saturn (Leo, sign 4) is house 2 from natal Moon (Cancer) -> setting phase.
    assert doshas["sade_sati"]["is_present"] is True
    assert "setting" in doshas["sade_sati"]["label"]
    # Sade Sati (12th/1st/2nd from Moon) and Dhaiya (4th/8th from Moon) are
    # mutually exclusive house sets — Saturn can't be in both at once.
    assert doshas["dhaiya"]["is_present"] is False
    assert doshas["kemadruma"]["is_present"] is False


def test_jupiter_transiting_moon_sign_flag_reflects_the_real_transit():
    reading = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))
    # Jupiter sits house 2 from Moon in this fixture, not house 1.
    assert reading["jupiter_transiting_moon_sign"] is False

    snapshot = _fake_snapshot(4, saturn_sign_index=4)
    snapshot.planet_house_from_moon["Ju"] = 1  # frozen dataclass, mutable dict field — legal
    conjunct = _build_reading(**_base_kwargs(transit_snapshot=snapshot))
    assert conjunct["jupiter_transiting_moon_sign"] is True


def test_life_growth_task_uses_ninth_house_lord():
    reading = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))
    assert "Jupiter" in reading["life_growth_task"]
    assert _FOCUS_BY_HOUSE_EN[9] in reading["life_growth_task"]


def test_transit_highlight_picks_saturn_when_it_sits_in_a_notable_house():
    reading = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))
    assert "Saturn" in reading["transit_highlight"]
    assert "8th house" in reading["transit_highlight"]


def test_moon_nakshatra_and_mood_tag_from_natal_longitude():
    reading = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))
    assert reading["moon_nakshatra"] == "Pushya"
    assert reading["moon_mood_tag"] == "calm and idealistic"


def test_hindi_language_produces_devanagari_text():
    reading = _build_reading(**_base_kwargs(language="hi", transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))
    assert "महादशा" in reading["mahadasha_label"]
    assert reading["decision_style"] != _build_reading(
        **_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4))
    )["decision_style"]


def test_panchang_fields_are_real_calculations():
    reading = _build_reading(**_base_kwargs(transit_snapshot=_fake_snapshot(4, saturn_sign_index=4)))
    # sun=10, moon=100 -> diff=90 -> tithi index 8 (Shukla Ashtami); sun at
    # longitude 10 -> Aries -> Vaishakha (amanta lunar month).
    assert reading["tithi_name"] == "Ashtami"
    assert reading["paksha"] == "shukla"
    assert reading["lunar_month"] == "Vaishakha"
    assert reading["festival"] is None  # an ordinary day in this fixture

    diwali = _build_reading(
        **_base_kwargs(
            transit_snapshot=_fake_snapshot(4, saturn_sign_index=4),
            sun_longitude_today=195.0,  # Sun in Libra -> Kartika
            moon_longitude_today=190.0,  # diff=(190-195)%360=355 -> tithi 30 -> Krishna Amavasya
            sun_longitude_yesterday=194.0,
        )
    )
    assert diwali["lunar_month"] == "Kartika"
    assert diwali["tithi_name"] == "Amavasya"
    assert diwali["festival"] == "Diwali (Amavasya)"
