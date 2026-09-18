from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ChatMessage(Base):
    """Text chat history for /chat/astro (voice chat uses this endpoint under
    the hood — the frontend does STT client-side or via /voice/transcribe
    first, then posts the transcript here)."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8))
    # Which Rishi persona this message belongs to (vasishtha/parashara/gargi/
    # agastya/bhrigu) — nullable because rows from before this column existed
    # have no persona recorded; those just don't surface in any one Rishi's
    # history rather than bleeding into all of them.
    rishi_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # True on an assistant reply that had non-empty structured Life Context
    # (or an open decision) available when it was composed — the raw input
    # to the "Context Utilization" metric (see app.services.metrics_service):
    # not just that personalization *could* apply, but that real personal
    # facts were actually on the table for that specific answer. Always
    # False on user-role rows.
    used_personalization: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
