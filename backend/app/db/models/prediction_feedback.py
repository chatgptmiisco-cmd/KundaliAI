from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class PredictionFeedback(Base):
    """Product spec §15/§30 — Historical Validation / Prediction Feedback:
    a real, falsifiable question the app actually asked the user (see
    app.api.v1.chat's vague-past-event fallback, _recent_past_candidate),
    and whether they confirmed, partially confirmed, denied, or never
    resolved it.

    Deliberately its own table, not a field bolted onto
    app.db.models.prediction_query_log.PredictionQueryLog: that table logs
    EVERY prediction call for history-nudge purposes, most of which are
    never followed up on and were never phrased as a question to answer —
    a row here only exists for the (much smaller) set of candidates that
    were actually surfaced as something to confirm.

    This never feeds back into the astrology calculation itself (see the
    product spec's "the LLM cannot compensate for incorrect deterministic
    astrology" principle) — a confirmed/partial answer only ever creates a
    real app.db.models.life_context.LifeEvent (see
    prediction_feedback_service.record_feedback), the same event-timeline
    entry a user stating a fact outright would create."""

    __tablename__ = "prediction_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # career | relationships | business | money | family — same vocabulary
    # as life_context_service.VALID_DOMAINS, or a "domain1+domain2" combo
    # string when _recent_past_candidate's cross-domain overlap detection
    # surfaced a combined candidate (see app.api.v1.chat).
    domain: Mapped[str] = mapped_column(String(64))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The actual question text shown to the user — kept so a later read
    # never has to re-derive "what was this even asking," and so
    # classify_message can recognize a reply as answering THIS specific
    # question rather than any other pending thing.
    question_asked: Mapped[str] = mapped_column(Text)
    # None until answered. correct | partial | incorrect | not_sure.
    feedback: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # What actually happened, in the user's own words — only meaningfully
    # populated for correct/partial; this is what becomes a LifeEvent.
    confirmed_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_prediction_feedback_user_pending", "user_id", "feedback"),)
