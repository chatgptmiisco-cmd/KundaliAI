"""Product spec §15/§30 — Historical Validation / Prediction Feedback: did a
real, falsifiable question the app actually asked (see app.api.v1.chat's
vague-past-event fallback) turn out to be right, partially right, wrong, or
never resolved. See app.db.models.prediction_feedback.PredictionFeedback for
why this is its own table rather than a field on PredictionQueryLog.

This never feeds back into the astrology calculation itself — a confirmed
answer only ever creates a real app.db.models.life_context.LifeEvent (see
record_feedback below), the same event-timeline entry a user stating a fact
outright would create."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.prediction_feedback import PredictionFeedback

VALID_FEEDBACK = {"correct", "partial", "incorrect", "not_sure"}


async def create_pending_feedback(
    db: AsyncSession, user_id: str, domain: str, window_start: datetime, window_end: datetime, question_asked: str
) -> PredictionFeedback:
    """Dedups on (user_id, domain, window_start, window_end) with
    feedback still unanswered — the SAME candidate window surfacing again
    across separate messages (the vague-past-event fallback has no memory
    of what it already asked) shouldn't spawn a duplicate pending row,
    mirroring life_context_service.upsert_decision's at-most-one-open
    convention."""
    result = await db.execute(
        select(PredictionFeedback).where(
            PredictionFeedback.user_id == user_id,
            PredictionFeedback.domain == domain,
            PredictionFeedback.window_start == window_start,
            PredictionFeedback.window_end == window_end,
            PredictionFeedback.feedback.is_(None),
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    row = PredictionFeedback(
        user_id=user_id, domain=domain, window_start=window_start, window_end=window_end,
        question_asked=question_asked,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_pending_feedback(db: AsyncSession, user_id: str) -> PredictionFeedback | None:
    """The most recently asked unanswered question, if any — at most one
    surfaced to classify_message per turn, same "one pending thing at a
    time" convention as get_decisions_due_for_outcome_checkin/
    get_facts_due_for_reconfirmation."""
    # Ordered by id, not created_at — two rows created within the same
    # server-clock tick (server_default=func.now()'s resolution) would
    # otherwise tie and fall back to whatever arbitrary order the DB
    # returns them in; id is a reliable insertion-order tiebreaker since
    # it's a real autoincrement column.
    result = await db.execute(
        select(PredictionFeedback)
        .where(PredictionFeedback.user_id == user_id, PredictionFeedback.feedback.is_(None))
        .order_by(PredictionFeedback.id.desc())
    )
    return result.scalars().first()


async def record_feedback(
    db: AsyncSession, user_id: str, feedback_id: int, feedback: str, confirmed_detail: str | None
) -> PredictionFeedback | None:
    if feedback not in VALID_FEEDBACK:
        return None
    result = await db.execute(
        select(PredictionFeedback).where(PredictionFeedback.id == feedback_id, PredictionFeedback.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.feedback = feedback
    row.confirmed_detail = confirmed_detail
    row.answered_at = datetime.now(timezone.utc)
    await db.commit()
    return row
