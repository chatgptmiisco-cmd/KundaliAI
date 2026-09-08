"""Daily horoscope: today's key transits relative to Lagna/Moon, turned into
plain-language text by the interpretation layer, cached once per
(user, date, language)."""
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.transits import compute_transit_snapshot
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import HoroscopeCache
from app.schemas.horoscope import DailyHoroscopeResponse
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_service import get_chart
from app.services.dasha_service import get_current_dasha
from app.services.interpretation.context import build_dasha_context, build_transit_context
from app.services.interpretation.factory import get_interpreter


def _select_stmt(profile: BirthProfile, for_date: date, language: str):
    return select(HoroscopeCache).where(
        HoroscopeCache.user_id == profile.user_id,
        HoroscopeCache.horoscope_date == for_date,
        HoroscopeCache.language == language,
    )


async def get_daily_horoscope(
    db: AsyncSession,
    profile: BirthProfile,
    birth: BirthDataOut,
    for_date: date,
    language: str,
    mode: str,
) -> DailyHoroscopeResponse:
    result = await db.execute(_select_stmt(profile, for_date, language))
    cached_row = result.scalar_one_or_none()
    if cached_row is not None:
        return DailyHoroscopeResponse(date=for_date, language=language, cached=True, **cached_row.data)

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")

    at = datetime(for_date.year, for_date.month, for_date.day, 12, 0, tzinfo=timezone.utc)
    snapshot = compute_transit_snapshot(at, d1.lagna_sign_index, moon.sign_index)

    context: dict = {"lagna_sign": d1.lagna_sign_name_hi if language == "hi" else d1.lagna_sign_name_en}
    context.update(build_transit_context(snapshot, language))  # type: ignore[arg-type]

    current_dasha = await get_current_dasha(db, profile, birth)
    if current_dasha is not None:
        context["antardasha_lord_key"] = current_dasha.antardasha.lord
        context["antardasha_lord"] = (
            current_dasha.antardasha.lord_name_hi if language == "hi" else current_dasha.antardasha.lord_name_en
        )

    interpreter = get_interpreter()
    generated = await interpreter.daily_horoscope(context, language, mode)  # type: ignore[arg-type]

    row = HoroscopeCache(user_id=profile.user_id, horoscope_date=for_date, language=language, data=generated)
    generated, was_race = await add_and_commit_or_fetch_existing(db, row, _select_stmt(profile, for_date, language))

    return DailyHoroscopeResponse(date=for_date, language=language, cached=was_race, **generated)
