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
    # Set only on an assistant-role row: an embedding of the WHOLE exchange
    # ("User: ...\nAssistant: ..."), JSON-encoded as a plain float list —
    # see app.services.chat_memory_service. Powers retrieval of older
    # conversation context that has fallen out of the raw recent-history
    # window (see chat.py's _HISTORY_LIMIT) but was never captured as a
    # durable structured fact (life_state/life_context) either. No pgvector
    # here deliberately (not installed on this dev Postgres, and unusable
    # on the SQLite test DB anyway) — similarity is computed in plain
    # Python, which is more than fast enough at one user's own message-
    # history scale. Never set on user-role rows.
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The exact "User: ...\nAssistant: ..." pair text the embedding above
    # was computed from — kept alongside it (rather than reconstructed from
    # `content`, which on this row is only the assistant's OWN reply) so a
    # retrieval hit can surface what the user actually said, not just how
    # it was answered. Always set together with `embedding`, never alone.
    embedding_source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
