"""Minimal admin endpoints: list users (PII masked), inspect one user's
subscription/profile status, and force-invalidate their cached content.
Real admin tooling (proper RBAC, audit UI, etc.) is out of scope for this
pass — these exist so support/ops has *something* without querying the DB
directly."""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_admin
from app.db.base import get_db
from app.db.models.cache import ChartCache, DashaCache, HoroscopeCache, PeriodAnalysisCache
from app.db.models.user import User
from app.schemas.admin import AdminRegenerateRequest, AdminUserDetail, AdminUserListItem
from app.services.payments.subscription_service import get_or_create_subscription
from app.services.user_service import get_birth_profile

router = APIRouter(prefix="/admin", tags=["admin"])


def _mask(value: str | None, keep: int = 2) -> str | None:
    if not value:
        return None
    if "@" in value:
        local, _, domain = value.partition("@")
        return f"{local[:keep]}{'*' * max(1, len(local) - keep)}@{domain}"
    return f"{value[:keep]}{'*' * max(1, len(value) - keep - 2)}{value[-2:]}"


@router.get("/users", response_model=list[AdminUserListItem])
async def list_users(
    limit: int = 50, offset: int = 0, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset))
    users = result.scalars().all()

    items = []
    for u in users:
        sub = await get_or_create_subscription(db, u.id)
        items.append(
            AdminUserListItem(
                id=u.id, email_masked=_mask(u.email), phone_masked=_mask(u.phone),
                tier=sub.tier, is_active=u.is_active, created_at=u.created_at,
            )
        )
    return items


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user_detail(
    user_id: str, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    sub = await get_or_create_subscription(db, user.id)
    profile = await get_birth_profile(db, user.id)

    return AdminUserDetail(
        id=user.id, email_masked=_mask(user.email), phone_masked=_mask(user.phone),
        preferred_language=user.preferred_language, tier=sub.tier, subscription_status=sub.status,
        has_birth_profile=profile is not None, is_active=user.is_active, is_admin=user.is_admin,
        created_at=user.created_at,
    )


@router.post("/regenerate", status_code=status.HTTP_204_NO_CONTENT)
async def regenerate(
    body: AdminRegenerateRequest, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
):
    """Deletes cached rows for the requested targets so the next request
    recomputes from scratch — useful after fixing a bug in the calculation
    or interpretation layer."""
    if "chart" in body.targets:
        await db.execute(delete(ChartCache).where(ChartCache.user_id == body.user_id))
    if "dasha" in body.targets:
        await db.execute(delete(DashaCache).where(DashaCache.user_id == body.user_id))
    if "horoscope" in body.targets:
        await db.execute(delete(HoroscopeCache).where(HoroscopeCache.user_id == body.user_id))
    if "analysis" in body.targets:
        await db.execute(delete(PeriodAnalysisCache).where(PeriodAnalysisCache.user_id == body.user_id))
    await db.commit()
