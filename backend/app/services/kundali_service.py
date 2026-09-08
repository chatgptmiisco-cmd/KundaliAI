"""The "Complete Kundali" view: basic details + 6 narrative sections +
brutal-truth summary + an embedded Manglik status + a lightweight summary
block (reused by the frontend's Home "at a glance" card so it doesn't need
its own endpoint). Cached per (user, language, birth-profile version).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.constants import NAKSHATRA_NAMES_EN, NAKSHATRA_NAMES_HI, NAKSHATRA_SPAN_DEG
from app.astro.ephemeris import julian_day_ut, planet_position
from app.astro.natal_insights import compute_natal_insights, planet_dignity
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import CompleteKundaliCache
from app.schemas.kundali import CompleteKundaliResponse, KeyValueItem, KundaliSection, KundaliSummary
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_service import birth_datetime_utc, get_chart
from app.services.dasha_service import get_current_dasha
from app.services.interpretation.factory import get_interpreter
from app.services.manglik_service import get_manglik_status

_SECTION_TITLES_EN = {
    "personality_nature": "Personality & Nature",
    "career_money": "Career & Money",
    "relationships_marriage": "Relationships & Marriage",
    "health_temperament": "Health & Temperament",
    "strengths_challenges": "Strengths & Challenges",
    "timing_overview": "Timing Overview",
}
_SECTION_TITLES_HI = {
    "personality_nature": "स्वभाव और व्यक्तित्व",
    "career_money": "करियर और धन",
    "relationships_marriage": "रिश्ते और विवाह",
    "health_temperament": "स्वास्थ्य और मिज़ाज",
    "strengths_challenges": "शक्तियां और चुनौतियां",
    "timing_overview": "समय विवरण",
}
_SECTION_ORDER = list(_SECTION_TITLES_EN.keys())


def _find_planet(chart, planet: str):
    return next(p for p in chart.planets if p.planet == planet)


def _select_stmt(profile: BirthProfile, language: str):
    return select(CompleteKundaliCache).where(
        CompleteKundaliCache.user_id == profile.user_id,
        CompleteKundaliCache.language == language,
        CompleteKundaliCache.birth_profile_version == profile.version,
    )


async def _get_or_compute(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, language: str, mode: str
) -> tuple[dict, bool]:
    result = await db.execute(_select_stmt(profile, language))
    cached_row = result.scalar_one_or_none()
    if cached_row is not None:
        return cached_row.data, True

    d1 = await get_chart(db, profile, birth, "D1")
    sun = _find_planet(d1, "Su")
    moon = _find_planet(d1, "Mo")

    jd_ut = julian_day_ut(birth_datetime_utc(birth))
    moon_longitude = planet_position(jd_ut, "Mo").longitude
    nakshatra_index = int((moon_longitude % 360) // NAKSHATRA_SPAN_DEG)
    nakshatra_name = (NAKSHATRA_NAMES_HI if language == "hi" else NAKSHATRA_NAMES_EN)[nakshatra_index]

    manglik = await get_manglik_status(db, profile, birth, language)
    current_dasha = await get_current_dasha(db, profile, birth)

    lagna_sign = d1.lagna_sign_name_hi if language == "hi" else d1.lagna_sign_name_en
    moon_sign = moon.sign_name_hi if language == "hi" else moon.sign_name_en
    sun_sign = sun.sign_name_hi if language == "hi" else sun.sign_name_en

    # Real, per-chart house-lord placements and planetary dignity — this is
    # what makes the six sections below describe THIS birth chart instead of
    # only varying by the current Mahadasha lord (see natal_insights docstring).
    planet_sign_index = {p.planet: p.sign_index for p in d1.planets}
    planet_house = {p.planet: p.house for p in d1.planets}
    insights = compute_natal_insights(d1.lagna_sign_index, planet_sign_index, planet_house)

    context: dict = {
        "lagna_sign": lagna_sign, "moon_sign": moon_sign, "sun_sign": sun_sign,
        "is_manglik": manglik.is_manglik,
        "lagna_lord_key": insights.lagna_lord,
        "lagna_lord_house": insights.lagna_lord_house,
        "lagna_lord_dignity": insights.planet_dignity.get(insights.lagna_lord, "neutral"),
        "tenth_lord_key": insights.tenth_lord,
        "tenth_lord_house": insights.tenth_lord_house,
        "tenth_lord_dignity": insights.planet_dignity.get(insights.tenth_lord, "neutral"),
        "seventh_lord_key": insights.seventh_lord,
        "seventh_lord_house": insights.seventh_lord_house,
        "seventh_lord_dignity": insights.planet_dignity.get(insights.seventh_lord, "neutral"),
        "sixth_lord_key": insights.sixth_lord,
        "sixth_lord_house": insights.sixth_lord_house,
        "sixth_lord_dignity": insights.planet_dignity.get(insights.sixth_lord, "neutral"),
        "strongest_planet_key": insights.strongest_planet,
        "weakest_planet_key": insights.weakest_planet,
    }
    if current_dasha is not None:
        context["mahadasha_lord_key"] = current_dasha.mahadasha.lord
        context["mahadasha_lord"] = current_dasha.mahadasha.lord_name_hi if language == "hi" else current_dasha.mahadasha.lord_name_en
        context["mahadasha_lord_house"] = planet_house.get(current_dasha.mahadasha.lord)
        context["mahadasha_lord_dignity"] = planet_dignity(
            current_dasha.mahadasha.lord, planet_sign_index[current_dasha.mahadasha.lord]
        )

    interpreter = get_interpreter()
    generated = await interpreter.complete_kundali(context, language, mode)  # type: ignore[arg-type]

    if language == "hi":
        basic_details = [
            {"label": "लग्न", "value": lagna_sign}, {"label": "चंद्र राशि", "value": moon_sign},
            {"label": "सूर्य राशि", "value": sun_sign}, {"label": "नक्षत्र", "value": nakshatra_name},
        ]
        manglik_one_liner = "आप मंगलिक हैं." if manglik.is_manglik else "आप मंगलिक नहीं हैं."
        titles = _SECTION_TITLES_HI
    else:
        basic_details = [
            {"label": "Lagna", "value": lagna_sign}, {"label": "Moon Sign", "value": moon_sign},
            {"label": "Sun Sign", "value": sun_sign}, {"label": "Nakshatra", "value": nakshatra_name},
        ]
        manglik_one_liner = "You are Manglik." if manglik.is_manglik else "You are not Manglik."
        titles = _SECTION_TITLES_EN

    sections = [
        {
            "id": section_id, "title": titles[section_id],
            "summary": generated["sections"][section_id]["summary"],
            "key_points": generated["sections"][section_id]["key_points"],
        }
        for section_id in _SECTION_ORDER
    ]

    data = {
        "basic_details": basic_details,
        "sections": sections,
        "manglik": manglik.model_dump(),
        "brutal_truth": generated["brutal_truth"],
        "summary": {
            "lagna": lagna_sign, "moon_sign": moon_sign,
            "core_strength": generated["core_strength"], "core_challenge": generated["core_challenge"],
            "is_manglik": manglik.is_manglik, "manglik_one_liner": manglik_one_liner,
        },
    }
    row = CompleteKundaliCache(user_id=profile.user_id, language=language, birth_profile_version=profile.version, data=data)
    return await add_and_commit_or_fetch_existing(db, row, _select_stmt(profile, language))


async def get_complete_kundali(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, language: str, mode: str
) -> CompleteKundaliResponse:
    data, cached = await _get_or_compute(db, profile, birth, language, mode)
    return CompleteKundaliResponse(
        language=language,
        basic_details=[KeyValueItem(**d) for d in data["basic_details"]],
        sections=[KundaliSection(**s) for s in data["sections"]],
        manglik=data["manglik"],
        brutal_truth=data["brutal_truth"],
        summary=KundaliSummary(**data["summary"]),
        cached=cached,
    )
