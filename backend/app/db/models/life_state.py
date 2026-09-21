from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class LifeState(Base):
    """One life-state row per user — the deterministic facts (married?
    children? pregnant? employed vs running a business?) that the
    Prediction Engine needs to decide WHICH question a chart is even
    answering, not just how strong a given astrological signal is. See
    app.services.prediction_service for how this reframes/redirects
    marriage_timing and life_event_timing(event_type="children").

    `marriage_date`/`expected_delivery` are encrypted at rest (see
    app.core.security.PiiCipher) — same treatment as BirthProfile's date
    fields, since a specific date is a meaningful quasi-identifier. The
    status/count fields stay plaintext, same split BirthProfile already
    makes between lat/long (plaintext) and name/dob/time/place (encrypted):
    low re-identification risk alone, and the engine reads them on every
    prediction request.

    `version` increments on every update and is stored inside cached
    marriage/life-event rows' JSON blob (alongside `algo_version`) so an
    edit here invalidates stale predictions without a cache-table migration
    — see prediction_service.py's `life_state_version` staleness check."""

    __tablename__ = "life_states"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)

    marital_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    marriage_date_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)

    children_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pregnancy_status: Mapped[str] = mapped_column(String(16), default="none", server_default="none")
    expected_delivery_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)

    career_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    business_state: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Phase 8 — property_purchase engine's life-state gate (spec §9/§23):
    # renting | owns_property | living_with_parents | other. Deliberately no
    # "considering_city_change" field — that's already tracked by Phase 3's
    # relocation_decision/LifeDecision(decision_type="relocation"); a second
    # parallel tracker for the same fact would be real duplication.
    housing_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    planning_property_purchase: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    has_home_loan: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
