from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ImportantDate(Base):
    """Phase 5 — unifies two of the spec's deferred items ("important
    dates" and "goal target dates") into one feature: a future date the
    user cares about (a deadline, an exam, an anniversary, a savings goal's
    target), worth checking back on once it passes. No push/scheduling
    infra exists in this backend, so this reuses the SAME "pull on next
    request" convention already shipped for outcome check-ins
    (life_context_service.get_decisions_due_for_outcome_checkin) and
    context decay (get_facts_due_for_reconfirmation) — see
    important_date_service.get_newly_passed."""

    __tablename__ = "important_dates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # career | business | money | relationships | family | goals |
    # preferences | identity — same vocabulary as life_context_service.
    # VALID_DOMAINS.
    domain: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    target_date: Mapped[date] = mapped_column(Date)
    # pending -> passed_unconfirmed (once target_date is in the past and
    # get_newly_passed has surfaced it once) -> resolved.
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_important_dates_user_status", "user_id", "status"),)
