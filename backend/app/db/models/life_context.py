from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class LifeContextItem(Base):
    """One structured fact about a user's real life, extracted from normal
    conversation (see app.services.chat_understanding's context_updates) —
    the general-purpose personalization memory described in the Life
    Context product spec, distinct from LifeState (a narrow, fixed-schema
    table of astrology-engine gating facts: married?/children?/employed vs
    business?) and from the old free-text UserMemoryNote it replaces.

    History, not overwrite: setting a new value for the same
    (user_id, domain, key) doesn't update the row in place — it marks the
    old one `status="superseded"` and inserts a new `active` row (see
    life_context_service.upsert_fact). Querying all rows for a key, oldest
    first, IS the history (e.g. salary_range over time) with no separate
    history table needed.

    `confidence`/`source` are what stop an LLM guess from silently becoming
    a "fact": "inferred" (the model's own read of the conversation, never
    directly stated) always starts at low/medium confidence, and only
    becomes source="user_confirmed" once the user has actually verified it
    when asked — see the product spec's "never treat AI inference as fact"
    principle."""

    __tablename__ = "life_context_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # career | business | money | relationships | family | goals | preferences | identity
    domain: Mapped[str] = mapped_column(String(32))
    # e.g. "occupation", "employer", "main_concern", "top_goal", "important_person:wife"
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text)

    confidence: Mapped[str] = mapped_column(String(16))  # high | medium | low
    source: Mapped[str] = mapped_column(String(24))  # user_stated | user_confirmed | inferred
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")  # active | superseded | deleted

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Bumped whenever the same fact is re-stated/re-confirmed without the
    # value actually changing — see life_context_service.upsert_fact. Used
    # for the spec's "context decay": a fact not reconfirmed in a long time
    # should be treated with lower confidence before being relied on.
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_life_context_user_domain_key", "user_id", "domain", "key"),
    )


class LifeDecision(Base):
    """A meaningful decision the user is actively weighing (e.g. "leave my
    job?", "start a business?") — tracked as its own object specifically so
    a later conversation can reference it ("last time we talked about this,
    you were still exploring") instead of starting over each time. Kept
    deliberately narrow in V1: `decision_type` is one of the two decision
    categories the chat classifier already detects (job_change_decision /
    business_start_decision), not an arbitrary open-ended decision — see
    life_context_service.upsert_decision."""

    __tablename__ = "life_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    decision_type: Mapped[str] = mapped_column(String(32))  # job_change | business_start
    context: Mapped[str | None] = mapped_column(Text, nullable=True)  # why, in the user's own terms
    status: Mapped[str] = mapped_column(String(16), default="exploring", server_default="exploring")  # exploring | decided | abandoned
    final_choice: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Outcome Follow-Ups (product spec §12): once `decided_at` is far enough
    # in the past, chat.py surfaces a check-in question on the user's next
    # NEW conversation — a pull-triggered check on an ordinary request
    # rather than a real scheduled push notification (this backend has no
    # job-scheduling/push infra), but "automatic" from the user's side:
    # they never have to ask for it, it just comes up next time they chat.
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_life_decisions_user_type", "user_id", "decision_type"),
    )


class LifeEvent(Base):
    """One entry in the user's Life Timeline (product spec §10) — a
    meaningful thing that happened, anchored to at least a year so it can
    be placed on a timeline and reasoned about ("your situation today is
    different from your 2024 situation because..."). Extracted the same way
    as LifeContextItem facts (see chat_understanding's `events` extraction),
    but kept as its own model since an event is a point in time, not a
    current-state fact that later gets superseded."""

    __tablename__ = "life_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    event_type: Mapped[str] = mapped_column(String(32))  # new_job | promotion | started_business | marriage | moved_city | became_parent | breakup | other
    description: Mapped[str] = mapped_column(Text)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-12, when known — most extracted events only have a year

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_life_events_user_year", "user_id", "year"),
    )
