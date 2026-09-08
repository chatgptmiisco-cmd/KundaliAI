"""Shared FastAPI dependencies: current-user resolution and the subscription
tier guard used to gate premium endpoints (D9/D10 interpretations, unlimited
period analyses, voice chat, voice chart explanations, decision planner)."""
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.base import get_db
from app.db.models.birth_profile import BirthProfile
from app.db.models.user import User
from app.services.payments.subscription_service import get_or_create_subscription
from app.services.user_service import get_birth_profile

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

_TIER_RANK = {"free": 0, "insight": 1, "strategy": 2}


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    request.state.user_id = user.id  # used by the rate limiter's key function
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


async def require_birth_profile(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> BirthProfile:
    profile = await get_birth_profile(db, user.id)
    if profile is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Birth details are required before generating a chart. Set them via PUT /user/profile first.",
        )
    return profile


def require_tier(minimum_tier: str) -> Callable:
    async def _checker(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
        if get_settings().all_features_free:
            return user
        subscription = await get_or_create_subscription(db, user.id)
        if _TIER_RANK[subscription.tier] < _TIER_RANK[minimum_tier]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"This feature requires the '{minimum_tier}' plan or higher (current: '{subscription.tier}').",
            )
        return user

    return _checker
