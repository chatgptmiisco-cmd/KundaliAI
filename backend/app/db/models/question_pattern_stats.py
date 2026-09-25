from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class QuestionPatternStats(Base):
    """Anonymized, aggregated cross-user learning — see the personal-
    astrologer chat upgrade plan's Phase 6. Deliberately carries NO user_id
    and NO question/answer text, ever: only counts per (category,
    target_domain, target_key), so a pattern useful for one user's situation
    can (softly, advisory-only) inform another user's without sharing any
    private content between them. Incremented from
    app.services.dynamic_question_service whenever a DynamicQuestionLog row
    is logged/answered/resolved.

    The three "usefulness" counters below are deliberately separate from
    times_asked/times_answered (which only measure whether a reply came
    back at all) — a question can be answered without the answer actually
    being usable, or without it resolving what was genuinely still missing.
    Populated where the signal is already available cheaply; a column can
    stay at 0 for a while without needing a schema change to start using it."""

    __tablename__ = "question_pattern_stats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    category: Mapped[str] = mapped_column(String(64))
    target_domain: Mapped[str] = mapped_column(String(32))
    target_key: Mapped[str] = mapped_column(String(64))

    times_asked: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    times_answered: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # The answer was actually referenced in a real reply (e.g. survived the
    # GPT interpretation layer's fact-preservation check), not just non-empty.
    times_answer_usable: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # This specific answer closed a `missing_information` gap
    # assess_and_generate_question had flagged.
    times_resolved_missing_information: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # answer_ready flipped false -> true immediately after this answer.
    times_answer_ready_after: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("category", "target_domain", "target_key", name="uq_question_pattern_stats_key"),
    )
