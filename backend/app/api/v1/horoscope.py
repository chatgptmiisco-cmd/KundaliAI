from datetime import date as date_type

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_birth_profile
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.db.models.birth_profile import BirthProfile
from app.schemas.horoscope import DailyHoroscopeResponse
from app.services import user_service
from app.services.horoscope_service import get_daily_horoscope

router = APIRouter(prefix="/horoscope", tags=["horoscope"])


@router.get("/daily", response_model=DailyHoroscopeResponse)
@limiter.limit("30/minute")
async def daily(
    request: Request,
    date: date_type = Query(default_factory=date_type.today),
    language: str = Query(default="en", pattern="^(en|hi)$"),
    mode: str = Query(default="simple", pattern="^(simple|detailed)$"),
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
):
    birth = user_service.decrypt_birth_data(profile)
    return await get_daily_horoscope(db, profile, birth, date, language, mode)
