from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class PredictionQueryLog(Base):
    """A running history of every Prediction Engine question a user has
    asked and what the engine answered — many rows per user (unlike
    BirthProfile/LifeState's one row per user), one per call to
    marriage-timing/life-event-timing/decision, logged regardless of
    whether that call was served from cache.

    `result_summary` is a SMALL structured summary (top window's dates/
    score/evidence_level for a timing call, or verdict/current-period-start
    for a decision) — not the full response payload — so later reads (see
    app.services.prediction_service.get_decision's history-nudge logic)
    don't need to parse prose to know what a past answer actually was.
    """

    __tablename__ = "prediction_query_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    intent: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str | None] = mapped_column(String(8), nullable=True)
    language: Mapped[str] = mapped_column(String(8))
    result_summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
