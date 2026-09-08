from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class BirthProfile(Base):
    """One birth profile per user (PII).

    `name`, `date_of_birth`, `time_of_birth` and `place_of_birth` are
    encrypted at rest (see app.core.security.PiiCipher) — the ORM stores and
    returns ciphertext; encryption/decryption happens in the service layer so
    it's explicit at every call site, not hidden behind a magic column type.

    Latitude/longitude/timezone are kept in plaintext: they're needed for
    every single chart calculation and are meaningfully less identifying than
    the place name string once detached from it.

    `version` increments on every update and is stamped onto every cached
    chart/dasha/horoscope/analysis row — a mismatch means "stale, recompute".
    """

    __tablename__ = "birth_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)

    name_encrypted: Mapped[str] = mapped_column(String(512))
    date_of_birth_encrypted: Mapped[str] = mapped_column(String(512))  # ISO date, encrypted
    time_of_birth_encrypted: Mapped[str] = mapped_column(String(512))  # HH:MM, encrypted
    time_uncertain: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    time_uncertainty_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    place_of_birth_encrypted: Mapped[str] = mapped_column(String(1024))

    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    timezone_offset_hours: Mapped[float] = mapped_column(Float)

    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
