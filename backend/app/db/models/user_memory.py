from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class UserMemoryNote(Base):
    """A short, LLM-extracted fact worth remembering about a user across chat
    sessions (e.g. "feeling low lately, cause unclear") — separate from raw
    ChatMessage history (verbatim, per-Rishi) and from LifeState (structured
    facts the Prediction Engine needs). This is unstructured, cross-Rishi
    context purely for personalizing future replies. Append-only; the most
    recent handful are read back (see user_memory_service.get_recent_notes),
    which bounds prompt size regardless of how large the table grows."""

    __tablename__ = "user_memory_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
