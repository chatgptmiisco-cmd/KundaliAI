"""Engine-owned follow-up state; user facts remain in the existing life model."""
from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversationState(Base):
    __tablename__ = "conversation_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rishi_id: Mapped[str] = mapped_column(String(32), default="")
    # MutableDict is required, not cosmetic: conversation_state is loaded once
    # and reused across a request, saved more than once (see chat.py), and
    # mutated in place between saves (e.g. resume()'s state[...] writes). A
    # plain JSON column can't see in-place dict mutations, so a later
    # save_state() silently no-ops when the dict object is unchanged by
    # identity — this previously made pending_situation_check vanish.
    data: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict)
    __table_args__ = (UniqueConstraint("user_id", "rishi_id", name="uq_conversation_state_user_rishi"),)
