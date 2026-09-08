"""Orchestrates the astro engine + DB-backed caching for D1/D9/D10 charts.

Cache key is (user_id, chart_type, birth_profile.version) — see
app.services.user_service.upsert_birth_profile for how a birth-data edit
invalidates every existing row by bumping the version instead of deleting
anything. Both languages' summary/key_points are generated and cached
together (same pattern as sign/planet names elsewhere in this API) so the
frontend can switch language without a second round-trip.
"""
from datetime import datetime, timedelta, timezone

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.charts import ChartResult, ChartType, compute_chart, degree_in_sign
from app.astro.constants import (
    NAKSHATRA_NAMES_EN,
    NAKSHATRA_NAMES_HI,
    NAKSHATRA_SPAN_DEG,
    PLANET_NAMES_EN,
    PLANET_NAMES_HI,
    SIGN_NAMES_EN,
    SIGN_NAMES_HI,
)
from app.astro.ephemeris import julian_day_ut
from app.astro.natal_insights import planet_dignity
from app.astro.panchang import nakshatra_pada
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import ChartCache
from app.schemas.chart import ChartResponse, HouseBreakdown, PlanetPlacement, YogaFinding
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_explanation_service import build_house_breakdown, detect_yogas
from app.services.interpretation.context import build_natal_context
from app.services.interpretation.factory import get_interpreter


def birth_datetime_utc(birth: BirthDataOut) -> datetime:
    hour, minute = (int(x) for x in birth.time_of_birth.split(":"))
    local_dt = datetime(
        birth.date_of_birth.year, birth.date_of_birth.month, birth.date_of_birth.day, hour, minute
    )
    return (local_dt - timedelta(hours=birth.timezone_offset_hours)).replace(tzinfo=timezone.utc)


def _format_degree(deg_in_sign: float) -> str:
    minutes = round((deg_in_sign % 1) * 60)
    degrees = int(deg_in_sign)
    if minutes == 60:  # rounding carried into the next whole degree
        minutes = 0
        degrees += 1
    return f"{degrees}°{minutes:02d}'"


def _nakshatra_index(longitude: float) -> int:
    return int((longitude % 360) // NAKSHATRA_SPAN_DEG)


def _chart_result_to_dict(result: ChartResult) -> dict:
    return {
        "chart_type": result.chart_type,
        "lagna_sign_index": result.lagna_sign_index,
        "lagna_longitude": result.lagna_longitude,
        "planet_sign_index": dict(result.planet_sign_index),
        "planet_house": dict(result.planet_house),
        "planet_retrograde": dict(result.planet_retrograde),
        "planet_longitude": dict(result.planet_longitude),
    }


def _dict_to_response(data: dict, cached: bool) -> ChartResponse:
    chart_type = data["chart_type"]
    planet_longitude: dict = data.get("planet_longitude", {})  # absent on rows cached before this field existed

    planets = []
    for planet, sign in data["planet_sign_index"].items():
        longitude = planet_longitude.get(planet)
        degree_display = None
        degree = None
        nakshatra_name_en = nakshatra_name_hi = None
        pada = None
        dignity = None
        if longitude is not None:
            # Exact degree-within-sign only makes sense for D1 — a D9/D10
            # sign is a discretized bucket, not a position with its own
            # continuous degree.
            if chart_type == "D1":
                degree = degree_in_sign(longitude)
                degree_display = _format_degree(degree)
            # Nakshatra/pada are real-longitude facts, unaffected by which
            # divisional chart is being viewed.
            nak_index = _nakshatra_index(longitude)
            nakshatra_name_en = NAKSHATRA_NAMES_EN[nak_index]
            nakshatra_name_hi = NAKSHATRA_NAMES_HI[nak_index]
            pada = nakshatra_pada(longitude)
            # Dignity is evaluated against whichever sign this varga places
            # the planet in (Rasi dignity for D1, Navamsa dignity for D9,
            # etc) — Rahu/Ketu are left as None rather than the misleading
            # "neutral" planet_dignity() falls back to when a planet has no
            # entry in the exaltation/debilitation/own-sign tables.
            if planet in ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa"):
                dignity = planet_dignity(planet, sign)

        planets.append(
            PlanetPlacement(
                planet=planet,
                planet_name_en=PLANET_NAMES_EN[planet],
                planet_name_hi=PLANET_NAMES_HI[planet],
                sign_index=sign,
                sign_name_en=SIGN_NAMES_EN[sign],
                sign_name_hi=SIGN_NAMES_HI[sign],
                house=data["planet_house"][planet],
                retrograde=data["planet_retrograde"][planet],
                degree_in_sign=degree,
                degree_display=degree_display,
                nakshatra_name_en=nakshatra_name_en,
                nakshatra_name_hi=nakshatra_name_hi,
                nakshatra_pada=pada,
                dignity=dignity,
            )
        )
    lagna_sign = data["lagna_sign_index"]
    lagna_longitude = data.get("lagna_longitude")
    lagna_degree = degree_in_sign(lagna_longitude) if lagna_longitude is not None and chart_type == "D1" else None
    return ChartResponse(
        chart_type=chart_type,
        lagna_sign_index=lagna_sign,
        lagna_sign_name_en=SIGN_NAMES_EN[lagna_sign],
        lagna_sign_name_hi=SIGN_NAMES_HI[lagna_sign],
        lagna_degree_in_sign=lagna_degree,
        lagna_degree_display=_format_degree(lagna_degree) if lagna_degree is not None else None,
        planets=planets,
        summary_en=data["summary_en"],
        summary_hi=data["summary_hi"],
        key_points_en=data["key_points_en"],
        key_points_hi=data["key_points_hi"],
        house_breakdown=[HouseBreakdown(**h) for h in data.get("house_breakdown", [])],
        yogas=[YogaFinding(**y) for y in data.get("yogas", [])],
        cached=cached,
    )


def _select_stmt(profile: BirthProfile, chart_type: ChartType):
    return select(ChartCache).where(
        ChartCache.user_id == profile.user_id,
        ChartCache.chart_type == chart_type,
        ChartCache.birth_profile_version == profile.version,
    )


async def get_chart(db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, chart_type: ChartType) -> ChartResponse:
    result = await db.execute(_select_stmt(profile, chart_type))
    cached_row = result.scalar_one_or_none()
    if cached_row is not None:
        return _dict_to_response(cached_row.data, cached=True)

    jd_ut = julian_day_ut(birth_datetime_utc(birth))
    chart_result = await anyio.to_thread.run_sync(
        compute_chart, jd_ut, birth.latitude, birth.longitude, chart_type
    )
    data = _chart_result_to_dict(chart_result)

    interpreter = get_interpreter()
    en_text = await interpreter.chart_summary(build_natal_context(chart_result, "en"), chart_type, "en", "simple")
    hi_text = await interpreter.chart_summary(build_natal_context(chart_result, "hi"), chart_type, "hi", "simple")
    data["summary_en"] = en_text["summary"]
    data["summary_hi"] = hi_text["summary"]
    data["key_points_en"] = en_text["key_points"]
    data["key_points_hi"] = hi_text["key_points"]

    data["house_breakdown"] = build_house_breakdown(chart_result)
    # Yoga/dosha detection (Gajakesari, Panch Mahapurusha, Raj Yoga, Manglik,
    # Kaal Sarp, Kemadruma) is a natal (D1) reading convention — a D9/D10
    # sign is a computed bucket, not a placement these classical checks apply to.
    data["yogas"] = detect_yogas(chart_result) if chart_type == "D1" else []

    row = ChartCache(user_id=profile.user_id, chart_type=chart_type, birth_profile_version=profile.version, data=data)
    data, was_race = await add_and_commit_or_fetch_existing(db, row, _select_stmt(profile, chart_type))

    return _dict_to_response(data, cached=was_race)
