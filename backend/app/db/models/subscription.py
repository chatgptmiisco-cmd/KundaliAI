from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Subscription(Base):
    """One subscription row per user. `tier` is the source of truth for
    access control (see app.api.deps.require_tier). Razorpay fields are
    populated once real payments are wired up; in stub mode they stay null
    and tier changes happen instantly via the simulated checkout endpoint."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)

    tier: Mapped[str] = mapped_column(String(16), default="free", server_default="free")  # free|insight|strategy
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    billing_cycle: Mapped[str | None] = mapped_column(String(16), nullable=True)  # monthly|yearly

    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    razorpay_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    razorpay_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
