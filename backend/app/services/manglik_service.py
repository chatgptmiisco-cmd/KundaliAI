"""Manglik status: derives the facts from the (already-cached) D1 chart,
then asks the interpretation layer to turn those facts into calm,
plain-language prose. Cached per (user, language, birth-profile version)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.manglik import compute_manglik_facts
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import ManglikCache
from app.schemas.chart import ChartResponse
from app.schemas.manglik import ManglikStatusResponse
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_service import get_chart
from app.services.interpretation.factory import get_interpreter


def _find_planet(chart: ChartResponse, planet: str):
    return next(p for p in chart.planets if p.planet == planet)


def _select_stmt(profile: BirthProfile, language: str):
    return select(ManglikCache).where(
        ManglikCache.user_id == profile.user_id,
        ManglikCache.language == language,
        ManglikCache.birth_profile_version == profile.version,
    )


async def _get_or_compute(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, language: str
) -> tuple[dict, bool]:
    result = await db.execute(_select_stmt(profile, language))
    cached_row = result.scalar_one_or_none()
    if cached_row is not None:
        return cached_row.data, True

    d1 = await get_chart(db, profile, birth, "D1")
    mars = _find_planet(d1, "Ma")
    moon = _find_planet(d1, "Mo")

    facts = compute_manglik_facts(
        mars_sign_index=mars.sign_index, mars_house_from_lagna=mars.house, moon_sign_index=moon.sign_index
    )

    context = {
        "is_manglik": facts.is_manglik,
        "mars_house_from_lagna": facts.mars_house_from_lagna,
        "mars_house_from_moon": facts.mars_house_from_moon,
        "mars_in_own_sign": facts.mars_in_own_sign,
        "lagna_sign": d1.lagna_sign_name_hi if language == "hi" else d1.lagna_sign_name_en,
    }

    interpreter = get_interpreter()
    generated = await interpreter.manglik_explanation(context, language, "simple")  # type: ignore[arg-type]

    data = {
        "is_manglik": facts.is_manglik,
        "mars_house_from_lagna": facts.mars_house_from_lagna,
        "mars_house_from_moon": facts.mars_house_from_moon,
        **generated,
    }
    row = ManglikCache(user_id=profile.user_id, language=language, birth_profile_version=profile.version, data=data)
    return await add_and_commit_or_fetch_existing(db, row, _select_stmt(profile, language))


async def get_manglik_status(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, language: str
) -> ManglikStatusResponse:
    data, cached = await _get_or_compute(db, profile, birth, language)
    return ManglikStatusResponse(cached=cached, **data)
