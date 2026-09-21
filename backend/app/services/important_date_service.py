"""Phase 5 — unifies the spec's deferred "important dates" and "goal target
dates" items: a future date the user cares about, worth checking back on
once it passes. No push/scheduling infra exists in this backend, so
`get_pending_checkin` reuses the SAME "pull on next request" convention
already shipped for outcome check-ins (life_context_service.
get_decisions_due_for_outcome_checkin) and context decay (get_facts_due_
for_reconfirmation) — see app.db.models.important_date.ImportantDate for
the full rationale.
"""
from datetime import date, datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.important_date import ImportantDate
from app.services import life_context_service


async def add_important_date(
    db: AsyncSession, user_id: str, domain: str, description: str, target_date: date
) -> ImportantDate:
    if domain not in life_context_service.VALID_DOMAINS:
        domain = "goals"
    row = ImportantDate(user_id=user_id, domain=domain, description=description, target_date=target_date)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_pending_checkin(db: AsyncSession, user_id: str) -> ImportantDate | None:
    """Promotes any `pending` row whose target_date has passed to
    `passed_unconfirmed` (idempotent — running this again promotes nothing
    new), then returns the oldest still-unconfirmed one, if any. Fetched
    UNCONDITIONALLY every turn (same convention as prediction_feedback_
    service.get_pending_feedback, not the "only at a fresh conversation's
    start" convention outcome-checkins use) so classify_message can
    recognize an answer arriving at any point in the conversation — the row
    persists as `passed_unconfirmed` across turns until actually resolved,
    unlike an outcome check-in's one-shot deterministic ask."""
    today = datetime.now(timezone.utc).date()
    await db.execute(
        update(ImportantDate)
        .where(ImportantDate.user_id == user_id, ImportantDate.status == "pending", ImportantDate.target_date < today)
        .values(status="passed_unconfirmed")
    )
    await db.commit()
    result = await db.execute(
        select(ImportantDate)
        .where(ImportantDate.user_id == user_id, ImportantDate.status == "passed_unconfirmed")
        .order_by(ImportantDate.target_date.asc())
    )
    return result.scalars().first()


async def resolve_important_date(
    db: AsyncSession, user_id: str, important_date_id: int, outcome_description: str | None
) -> ImportantDate | None:
    """Sets `resolved`, and — when the user actually described what
    happened — also records a real LifeEvent, the same "a confirmed answer
    becomes a real event" convention prediction_feedback_service.
    record_feedback already uses for the vague-past-event fallback."""
    result = await db.execute(
        select(ImportantDate).where(ImportantDate.id == important_date_id, ImportantDate.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.status = "resolved"
    row.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    if outcome_description:
        await life_context_service.add_event(db, user_id, "other", outcome_description, row.target_date.year, row.target_date.month)
    return row
