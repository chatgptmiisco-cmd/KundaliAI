"""Signup / login. Email+password is fully real; phone+OTP is a working dev
stub (the code is returned in the API response instead of sent via SMS);
OAuth is not implemented yet (raises NotImplementedError with a clear
message) since verifying a real Google/Apple id_token needs their SDKs and
client credentials, which is exactly the kind of "needs real credentials"
piece this pass intentionally left as a documented extension point.
"""
import random
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.subscription import Subscription
from app.db.models.user import OtpRequest, User

OTP_TTL_SECONDS = 300


class AuthError(Exception):
    pass


async def _ensure_subscription(db: AsyncSession, user_id: str) -> None:
    db.add(Subscription(user_id=user_id, tier="free", status="active"))


async def signup_with_email(
    db: AsyncSession, email: str, password: str, name: str, preferred_language: str
) -> User:
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise AuthError("An account with this email already exists.")

    user = User(
        email=email,
        hashed_password=hash_password(password),
        preferred_language=preferred_language,
    )
    db.add(user)
    await db.flush()
    await _ensure_subscription(db, user.id)
    await db.commit()
    await db.refresh(user)
    return user


async def login_with_email(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or user.hashed_password is None or not verify_password(password, user.hashed_password):
        raise AuthError("Invalid email or password.")
    if not user.is_active:
        raise AuthError("This account has been deactivated.")
    return user


async def request_otp(db: AsyncSession, phone: str) -> tuple[str, int]:
    """Dev-mode OTP: generates and stores a real code with a real expiry, but
    returns it in the response instead of sending an SMS. Swap the "return
    code" behaviour for a real SMS provider call (MSG91/Twilio/etc.) without
    changing verify_otp at all."""
    code = "".join(random.choices(string.digits, k=6))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS)
    db.add(OtpRequest(phone=phone, code=code, expires_at=expires_at))
    await db.commit()
    return code, OTP_TTL_SECONDS


async def verify_otp(db: AsyncSession, phone: str, code: str) -> User:
    result = await db.execute(
        select(OtpRequest)
        .where(OtpRequest.phone == phone, OtpRequest.consumed.is_(False))
        .order_by(OtpRequest.created_at.desc())
    )
    otp = result.scalars().first()
    now = datetime.now(timezone.utc)
    if otp is None or otp.code != code or otp.expires_at.replace(tzinfo=timezone.utc) < now:
        raise AuthError("Invalid or expired code.")

    otp.consumed = True

    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(phone=phone)
        db.add(user)
        await db.flush()
        await _ensure_subscription(db, user.id)

    await db.commit()
    await db.refresh(user)
    return user


async def oauth_login(db: AsyncSession, provider: str, id_token: str) -> User:
    raise NotImplementedError(
        f"OAuth login via '{provider}' is not wired up yet — verifying a real "
        "Google/Apple id_token needs their SDK and your OAuth client credentials. "
        "Use email/password or phone+OTP for now."
    )


def issue_token(user: User) -> str:
    return create_access_token(subject=user.id)
