from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_birth_profile
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.db.models.birth_profile import BirthProfile
from app.db.models.user import User
from app.schemas.analysis import PeriodAnalysisRequest, PeriodAnalysisResponse
from app.services import user_service
from app.services.analysis_service import QuotaExceededError, get_period_analysis
from app.services.i18n.i18n_service import t
from app.services.payments.subscription_service import get_or_create_subscription

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/period", response_model=PeriodAnalysisResponse)
@limiter.limit("10/minute")
async def period_analysis(
    request: Request,
    body: PeriodAnalysisRequest,
    profile: BirthProfile = Depends(require_birth_profile),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    birth = user_service.decrypt_birth_data(profile)
    subscription = await get_or_create_subscription(db, user.id)
    try:
        return await get_period_analysis(db, profile, birth, body, subscription.tier)
    except QuotaExceededError as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, t("quota_exceeded", body.language)) from exc
