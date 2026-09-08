import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)

    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    oauth_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 'google' | 'apple'
    oauth_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)

    preferred_language: Mapped[str] = mapped_column(String(16), default="en", server_default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OtpRequest(Base):
    """Stubbed phone-OTP flow. In dev/test the code is always returned in the
    API response (never sent via SMS); wiring a real provider (MSG91/Twilio/
    etc.) means generating a random code and sending it instead, without
    changing the endpoint contract."""

    __tablename__ = "otp_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(32), index=True)
    code: Mapped[str] = mapped_column(String(8))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
