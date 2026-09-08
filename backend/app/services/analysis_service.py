"""Period analysis: natal chart + current dasha + a representative transit
snapshot, turned into a rated theme/risks/opportunities/summary by the
interpretation layer. Free tier is quota-limited per calendar month; Insight
and Strategy are unlimited (see app.api.deps for the tier check itself —
this module only tracks/enforces the *count*)."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.transits import compute_transit_snapshot
from app.core.config import get_settings
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import PeriodAnalysisCache, UsageCounter
from app.schemas.analysis import PeriodAnalysisRequest, PeriodAnalysisResponse
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_service import get_chart
from app.services.dasha_service import get_current_dasha
from app.services.interpretation.context import build_transit_context
from app.services.interpretation.factory import get_interpreter

_METRIC = "period_analysis"


class QuotaExceededError(Exception):
    pass


async def _remaining_free_quota(db: AsyncSession, user_id: str) -> int:
    settings = get_settings()
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    result = await db.execute(
        select(UsageCounter).where(
            UsageCounter.user_id == user_id, UsageCounter.metric == _METRIC, UsageCounter.year_month == year_month
        )
    )
    counter = result.scalar_one_or_none()
    used = counter.count if counter else 0
    return max(0, settings.free_monthly_period_analyses - used)


async def _increment_usage(db: AsyncSession, user_id: str) -> None:
    year_month = datetime.now(timezone.utc).strftime("%Y-%m")
    result = await db.execute(
        select(UsageCounter).where(
            UsageCounter.user_id == user_id, UsageCounter.metric == _METRIC, UsageCounter.year_month == year_month
        )
    )
    counter = result.scalar_one_or_none()
    if counter is None:
        db.add(UsageCounter(user_id=user_id, metric=_METRIC, year_month=year_month, count=1))
    else:
        counter.count += 1
    await db.commit()


async def get_period_analysis(
    db: AsyncSession,
    profile: BirthProfile,
    birth: BirthDataOut,
    request: PeriodAnalysisRequest,
    subscription_tier: str,
) -> PeriodAnalysisResponse:
    # ALL_FEATURES_FREE unlocks unlimited period analyses for every tier
    # while pricing isn't live yet (see app.core.config) — the subscription
    # tier itself is untouched, only the quota enforcement is skipped.
    is_free = subscription_tier == "free" and not get_settings().all_features_free

    select_stmt = select(PeriodAnalysisCache).where(
        PeriodAnalysisCache.user_id == profile.user_id,
        PeriodAnalysisCache.start_date == request.start_date,
        PeriodAnalysisCache.end_date == request.end_date,
        PeriodAnalysisCache.language == request.language,
        PeriodAnalysisCache.birth_profile_version == profile.version,
    )
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    remaining = await _remaining_free_quota(db, profile.user_id) if is_free else None

    if cached_row is not None:
        return PeriodAnalysisResponse(
            start_date=request.start_date, end_date=request.end_date, language=request.language,
            cached=True, remaining_free_analyses_this_month=remaining, **cached_row.data,
        )

    if is_free and remaining is not None and remaining <= 0:
        raise QuotaExceededError()

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")

    midpoint = request.start_date + (request.end_date - request.start_date) / 2
    at = datetime(midpoint.year, midpoint.month, midpoint.day, 12, 0, tzinfo=timezone.utc)
    snapshot = compute_transit_snapshot(at, d1.lagna_sign_index, moon.sign_index)

    context: dict = {"lagna_sign": d1.lagna_sign_name_hi if request.language == "hi" else d1.lagna_sign_name_en}
    context.update(build_transit_context(snapshot, request.language))  # type: ignore[arg-type]

    current_dasha = await get_current_dasha(db, profile, birth)
    if current_dasha is not None:
        context["mahadasha_lord_key"] = current_dasha.mahadasha.lord
        context["antardasha_lord_key"] = current_dasha.antardasha.lord
        context["mahadasha_lord"] = (
            current_dasha.mahadasha.lord_name_hi if request.language == "hi" else current_dasha.mahadasha.lord_name_en
        )
        context["antardasha_lord"] = (
            current_dasha.antardasha.lord_name_hi if request.language == "hi" else current_dasha.antardasha.lord_name_en
        )

    interpreter = get_interpreter()
    generated = await interpreter.period_analysis(context, request.language, request.mode)  # type: ignore[arg-type]

    row = PeriodAnalysisCache(
        user_id=profile.user_id, start_date=request.start_date, end_date=request.end_date,
        language=request.language, birth_profile_version=profile.version, data=generated,
    )
    generated, was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)

    if is_free:
        # If a concurrent identical request won the race, it already
        # incremented usage — don't double-count this one.
        if not was_race:
            await _increment_usage(db, profile.user_id)
        remaining = await _remaining_free_quota(db, profile.user_id)

    return PeriodAnalysisResponse(
        start_date=request.start_date, end_date=request.end_date, language=request.language,
        cached=was_race, remaining_free_analyses_this_month=remaining, **generated,
    )
