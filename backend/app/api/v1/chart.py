from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_birth_profile, require_tier
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.db.models.birth_profile import BirthProfile
from app.schemas.chart import ChartResponse
from app.services import user_service
from app.services.chart_service import get_chart

router = APIRouter(prefix="/chart", tags=["chart"])


@router.get("/d1", response_model=ChartResponse)
@limiter.limit("30/minute")
async def get_d1(
    request: Request, profile: BirthProfile = Depends(require_birth_profile), db: AsyncSession = Depends(get_db)
):
    birth = user_service.decrypt_birth_data(profile)
    return await get_chart(db, profile, birth, "D1")


@router.get("/d9", response_model=ChartResponse)
@limiter.limit("30/minute")
async def get_d9(
    request: Request,
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_tier("insight")),
):
    birth = user_service.decrypt_birth_data(profile)
    return await get_chart(db, profile, birth, "D9")


@router.get("/d10", response_model=ChartResponse)
@limiter.limit("30/minute")
async def get_d10(
    request: Request,
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_tier("insight")),
):
    birth = user_service.decrypt_birth_data(profile)
    return await get_chart(db, profile, birth, "D10")
