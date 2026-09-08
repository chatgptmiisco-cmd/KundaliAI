from datetime import date as date_type

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_birth_profile
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.db.models.birth_profile import BirthProfile
from app.schemas.daily_reading import DailyReadingResponse
from app.schemas.focus_reading import FocusReadingsResponse
from app.schemas.guna_milan import GunaMilanRequest, GunaMilanResponse
from app.schemas.kundali import CompleteKundaliResponse
from app.schemas.manglik import ManglikStatusResponse
from app.schemas.validation import ValidationQuestionsResponse
from app.services import user_service
from app.services.daily_reading_service import get_daily_reading
from app.services.focus_reading_service import get_focus_readings
from app.services.guna_milan_service import get_guna_milan
from app.services.kundali_service import get_complete_kundali
from app.services.manglik_service import get_manglik_status
from app.services.validation_service import get_validation_questions

router = APIRouter(prefix="/kundali", tags=["kundali"])


@router.get("/daily-reading", response_model=DailyReadingResponse)
@limiter.limit("30/minute")
async def daily_reading(
    request: Request,
    date: date_type = Query(default_factory=date_type.today),
    language: str = Query(default="en", pattern="^(en|hi)$"),
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
):
    birth = user_service.decrypt_birth_data(profile)
    return await get_daily_reading(db, profile, birth, date, language)


@router.get("/focus-readings", response_model=FocusReadingsResponse)
@limiter.limit("30/minute")
async def focus_readings(
    request: Request,
    date: date_type = Query(default_factory=date_type.today),
    language: str = Query(default="en", pattern="^(en|hi)$"),
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
):
    birth = user_service.decrypt_birth_data(profile)
    return await get_focus_readings(db, profile, birth, date, language)


@router.get("/complete", response_model=CompleteKundaliResponse)
@limiter.limit("10/minute")
async def complete_kundali(
    request: Request,
    language: str = Query(default="en", pattern="^(en|hi)$"),
    mode: str = Query(default="simple", pattern="^(simple|detailed)$"),
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
):
    birth = user_service.decrypt_birth_data(profile)
    return await get_complete_kundali(db, profile, birth, language, mode)


@router.get("/manglik", response_model=ManglikStatusResponse)
@limiter.limit("10/minute")
async def manglik(
    request: Request,
    language: str = Query(default="en", pattern="^(en|hi)$"),
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
):
    birth = user_service.decrypt_birth_data(profile)
    return await get_manglik_status(db, profile, birth, language)


@router.get("/validation-questions", response_model=ValidationQuestionsResponse)
@limiter.limit("10/minute")
async def validation_questions(
    request: Request,
    language: str = Query(default="en", pattern="^(en|hi)$"),
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
):
    birth = user_service.decrypt_birth_data(profile)
    return await get_validation_questions(db, profile, birth, language)


@router.post("/guna-milan", response_model=GunaMilanResponse)
@limiter.limit("10/minute")
async def guna_milan(
    request: Request,
    body: GunaMilanRequest,
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
):
    birth = user_service.decrypt_birth_data(profile)
    return await get_guna_milan(db, profile, birth, body)
