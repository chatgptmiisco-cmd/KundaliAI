from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_birth_profile
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.db.models.birth_profile import BirthProfile
from app.schemas.dasha import CurrentDashaResponse, DashaTimelineResponse
from app.services import user_service
from app.services.dasha_service import get_current_dasha, get_dasha_timeline

router = APIRouter(prefix="/dasha", tags=["dasha"])


@router.get("/timeline", response_model=DashaTimelineResponse)
@limiter.limit("30/minute")
async def timeline(
    request: Request, profile: BirthProfile = Depends(require_birth_profile), db: AsyncSession = Depends(get_db)
):
    birth = user_service.decrypt_birth_data(profile)
    return await get_dasha_timeline(db, profile, birth)


@router.get("/current", response_model=CurrentDashaResponse)
@limiter.limit("30/minute")
async def current(
    request: Request, profile: BirthProfile = Depends(require_birth_profile), db: AsyncSession = Depends(get_db)
):
    birth = user_service.decrypt_birth_data(profile)
    result = await get_current_dasha(db, profile, birth)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Could not determine current dasha")
    return result
