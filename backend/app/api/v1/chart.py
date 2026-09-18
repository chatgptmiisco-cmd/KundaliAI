from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_birth_profile, require_tier
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.db.models.birth_profile import BirthProfile
from app.db.models.user import User
from app.schemas.chart import AdhocChartIn, ChartResponse
from app.services import user_service
from app.services.chart_service import compute_adhoc_chart, get_chart

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


@router.post("/lookup", response_model=ChartResponse)
@limiter.limit("20/minute")
async def lookup_chart(
    request: Request,
    body: AdhocChartIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """"Check someone else's chart" — a family member's, say — without
    overwriting the signed-in user's own saved birth profile. D9/D10 stay
    behind the same paywall as the user's own divisional charts (calling
    require_tier's checker directly here, rather than via Depends, since
    which tier applies depends on `body.chart_type`, not a fixed route)."""
    if body.chart_type in ("D9", "D10"):
        await require_tier("insight")(user=user, db=db)
    return await compute_adhoc_chart(body)
