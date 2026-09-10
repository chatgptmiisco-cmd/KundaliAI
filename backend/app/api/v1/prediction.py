from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_birth_profile
from app.astro.life_event_timing import EventType
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.db.models.birth_profile import BirthProfile
from app.schemas.prediction import (
    LifeEventTimingResponse,
    MarriageTimingResponse,
    MultiYearOutlookResponse,
    YearOutlookResponse,
)
from app.services import prediction_service, user_service
from app.services.interpretation.base import Language

router = APIRouter(prefix="/prediction", tags=["prediction"])

# A requested year must stay within a few years of "now" — a real, useful
# outlook window, not an open door to computing decades of solar returns per
# request. MultiYear already caps its own span (MAX_MULTI_YEARS) on top of this.
_MAX_YEARS_AHEAD = 3


@router.get("/year-ahead", response_model=YearOutlookResponse)
@limiter.limit("20/minute")
async def year_ahead(
    request: Request,
    year: int | None = Query(default=None),
    language: Language = Query(default="en"),
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
):
    current_year = datetime.now(timezone.utc).year
    target_year = year if year is not None else current_year
    target_year = max(current_year, min(target_year, current_year + _MAX_YEARS_AHEAD))
    birth = user_service.decrypt_birth_data(profile)
    return await prediction_service.get_year_ahead(db, profile, birth, target_year, language)


@router.get("/multi-year", response_model=MultiYearOutlookResponse)
@limiter.limit("10/minute")
async def multi_year(
    request: Request,
    years: int = Query(default=2, ge=1, le=prediction_service.MAX_MULTI_YEARS),
    language: Language = Query(default="en"),
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
):
    birth = user_service.decrypt_birth_data(profile)
    return await prediction_service.get_multi_year_outlook(db, profile, birth, years, language)


@router.get("/marriage-timing", response_model=MarriageTimingResponse)
@limiter.limit("20/minute")
async def marriage_timing(
    request: Request,
    language: Language = Query(default="en"),
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
):
    birth = user_service.decrypt_birth_data(profile)
    return await prediction_service.get_marriage_timing(db, profile, birth, language)


@router.get("/life-event-timing", response_model=LifeEventTimingResponse)
@limiter.limit("20/minute")
async def life_event_timing(
    request: Request,
    event_type: EventType = Query(...),
    language: Language = Query(default="en"),
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
):
    birth = user_service.decrypt_birth_data(profile)
    return await prediction_service.get_life_event_timing(db, profile, birth, event_type, language)
