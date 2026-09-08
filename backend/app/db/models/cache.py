from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ChartCache(Base):
    """Computed D1/D9/D10 chart, cached per (user, chart_type, birth profile
    version). A birth-data edit bumps BirthProfile.version, which makes every
    existing row here stale without needing to delete anything."""

    __tablename__ = "chart_cache"
    __table_args__ = (UniqueConstraint("user_id", "chart_type", "birth_profile_version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chart_type: Mapped[str] = mapped_column(String(8))  # D1 | D9 | D10
    birth_profile_version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DashaCache(Base):
    __tablename__ = "dasha_cache"
    __table_args__ = (UniqueConstraint("user_id", "birth_profile_version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    birth_profile_version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HoroscopeCache(Base):
    __tablename__ = "horoscope_cache"
    __table_args__ = (UniqueConstraint("user_id", "horoscope_date", "language"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    horoscope_date: Mapped[date] = mapped_column(Date)
    language: Mapped[str] = mapped_column(String(8))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PeriodAnalysisCache(Base):
    __tablename__ = "period_analysis_cache"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "start_date", "end_date", "language", "birth_profile_version"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    language: Mapped[str] = mapped_column(String(8))
    birth_profile_version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ManglikCache(Base):
    __tablename__ = "manglik_cache"
    __table_args__ = (UniqueConstraint("user_id", "language", "birth_profile_version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    language: Mapped[str] = mapped_column(String(8))
    birth_profile_version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompleteKundaliCache(Base):
    """The full narrative kundali (6 sections + brutal truth), cached per
    (user, language, birth profile version) — the most expensive LLM call in
    the API, so worth its own cache row."""

    __tablename__ = "complete_kundali_cache"
    __table_args__ = (UniqueConstraint("user_id", "language", "birth_profile_version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    language: Mapped[str] = mapped_column(String(8))
    birth_profile_version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyReadingCache(Base):
    """The full per-user "today" reading (rating/theme/risks/doshas/etc.),
    cached per (user, date, language, birth-profile version) — a birth-data
    edit or a new day both invalidate it the same way ChartCache/HoroscopeCache
    already do."""

    __tablename__ = "daily_reading_cache"
    __table_args__ = (UniqueConstraint("user_id", "reading_date", "language", "birth_profile_version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reading_date: Mapped[date] = mapped_column(Date)
    language: Mapped[str] = mapped_column(String(8))
    birth_profile_version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FocusReadingCache(Base):
    """Per-focus-area "how is today for this part of my life" readings
    (family/health/career/marriage/friends), cached per (user, date,
    language, birth-profile version) — same invalidation story as
    DailyReadingCache."""

    __tablename__ = "focus_reading_cache"
    __table_args__ = (UniqueConstraint("user_id", "reading_date", "language", "birth_profile_version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reading_date: Mapped[date] = mapped_column(Date)
    language: Mapped[str] = mapped_column(String(8))
    birth_profile_version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageCounter(Base):
    """Tracks free-tier monthly quota usage (e.g. deep period analyses)."""

    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("user_id", "metric", "year_month"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    metric: Mapped[str] = mapped_column(String(64))  # e.g. "period_analysis"
    year_month: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"
    count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
