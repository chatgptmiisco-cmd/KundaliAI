"""Structured, progressively-built user context — see app.db.models.
life_context for the data model and the product spec this implements
(Life Context Capture V1). Two things live here:

  1. Facts (LifeContextItem): domain/key/value with confidence + source,
     upserted from chat extraction (app.services.chat_understanding) —
     never overwritten in place, so querying history for a (domain, key)
     is just "every row ever inserted for it," oldest first.
  2. Decisions (LifeDecision): a meaningful choice the user is actively
     weighing, referenced across conversations instead of re-litigated
     from scratch each time.

Retrieval is deliberately scoped (get_active_context takes an optional
domain filter) — the chat pipeline only pulls the domains relevant to
whatever the user actually asked about, not their entire life context on
every turn (see the product spec's "retrieve only relevant context")."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.life_context import LifeContextItem, LifeDecision, LifeEvent

VALID_DOMAINS = {
    "identity", "career", "business", "money", "relationships", "family", "goals", "preferences",
}
VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_SOURCE = {"user_stated", "user_confirmed", "inferred"}

# Product spec §13 — Context Decay: domains where a fact is realistically
# likely to go stale (a job, a relationship, a business, an income level)
# are worth periodically re-confirming; static/slow-changing ones
# (identity, goals, preferences) are left alone rather than nagging the
# user about something that essentially never changes.
_RECONFIRM_DOMAINS = ("career", "business", "relationships", "money")
_CONFIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}
_CONFIDENCE_BY_RANK = {2: "high", 1: "medium", 0: "low"}
# One confidence step down for every this-many days a fact goes without
# being reconfirmed (a re-statement of the same value through upsert_fact,
# or an explicit reconfirmation — see get_facts_due_for_reconfirmation).
_DECAY_STEP_DAYS = 120

# job_change/business_start/relocation are the decision types the chat
# classifier can currently detect (job_change_decision/business_start_
# decision/relocation_decision categories) — kept this narrow deliberately,
# see LifeDecision's docstring. relocation_decision has no get_decision
# verdict engine behind it (see app.api.v1.chat's relocation block) — it
# reuses the existing foreign_travel life-event-timing signal instead of
# inventing a new astrological rule for "should I move."
_DECISION_TYPE_BY_CATEGORY = {
    "job_change_decision": "job_change",
    "business_start_decision": "business_start",
    "relocation_decision": "relocation",
    # Phase 5: house_purchase_decision is fully generic (get_decision's own
    # _DECISION_EVENT_TYPE/_DECISION_HOUSE, new EventType="property");
    # marriage_decision deliberately bypasses get_decision entirely (see
    # prediction_service.get_marriage_decision) but is tracked here exactly
    # like the others — Decision Memory tracking has no idea which engine
    # call backed a decision, only its category<->type mapping.
    "house_purchase_decision": "house_purchase",
    "marriage_decision": "marriage",
    "investment_decision": "investment",
}
CATEGORY_BY_DECISION_TYPE = {v: k for k, v in _DECISION_TYPE_BY_CATEGORY.items()}


async def upsert_fact(
    db: AsyncSession, user_id: str, domain: str, key: str, value: str, confidence: str, source: str
) -> LifeContextItem:
    """Records a new value for (user_id, domain, key). If the value is
    unchanged from the current active fact, this only refreshes
    last_confirmed_at (the spec's "context decay" needs to know when a fact
    was last reconfirmed, not just when it was first captured) rather than
    creating a needless duplicate history row. A genuinely different value
    supersedes the old row and inserts a new one, preserving history."""
    domain = domain if domain in VALID_DOMAINS else "preferences"
    confidence = confidence if confidence in VALID_CONFIDENCE else "medium"
    source = source if source in VALID_SOURCE else "inferred"

    result = await db.execute(
        select(LifeContextItem).where(
            LifeContextItem.user_id == user_id,
            LifeContextItem.domain == domain,
            LifeContextItem.key == key,
            LifeContextItem.status == "active",
        )
    )
    existing = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if existing is not None and existing.value == value:
        existing.last_confirmed_at = now
        # A re-statement is itself a weak confirmation signal — never
        # downgrades confidence, but can upgrade it (e.g. inferred said
        # twice independently, or the user directly confirmed what was
        # previously only inferred).
        rank = {"low": 0, "medium": 1, "high": 2}
        if rank[confidence] > rank[existing.confidence]:
            existing.confidence = confidence
        if source == "user_confirmed":
            existing.source = source
        await db.commit()
        return existing

    if existing is not None:
        existing.status = "superseded"

    item = LifeContextItem(
        user_id=user_id, domain=domain, key=key, value=value,
        confidence=confidence, source=source, last_confirmed_at=now,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


def effective_confidence(confidence: str, last_confirmed_at: datetime | None) -> str:
    """Product spec §13 — Context Decay: confidence isn't permanent. A fact
    that hasn't been reconfirmed in a while is progressively less safe to
    lean on, so every _DECAY_STEP_DAYS without reconfirmation drops it one
    rank (floored at "low") for any READER (chat personalization, the My
    Life Twin screen) — this never mutates the stored row, only what
    callers are told to treat it as. See get_facts_due_for_reconfirmation
    for what happens once a fact has decayed all the way to "low"."""
    if last_confirmed_at is None:
        return confidence
    # SQLite round-trips DateTime columns as naive (drops the tzinfo we set
    # them with) — treat a naive value as UTC rather than let the
    # subtraction below raise.
    if last_confirmed_at.tzinfo is None:
        last_confirmed_at = last_confirmed_at.replace(tzinfo=timezone.utc)
    days_stale = (datetime.now(timezone.utc) - last_confirmed_at).days
    steps_down = days_stale // _DECAY_STEP_DAYS
    rank = max(0, _CONFIDENCE_RANK.get(confidence, 1) - steps_down)
    return _CONFIDENCE_BY_RANK[rank]


def memory_relevance(status: str, last_confirmed_at: datetime | None, now: datetime | None = None) -> str:
    """Relevance is not confidence: a true old plan need not be today's intent."""
    if status != "active":
        return "INACTIVE"
    if last_confirmed_at is None:
        return "HISTORICAL"
    confirmed = last_confirmed_at.replace(tzinfo=timezone.utc) if last_confirmed_at.tzinfo is None else last_confirmed_at
    days = ((now or datetime.now(timezone.utc)) - confirmed).days
    return "ACTIVE" if days <= 7 else "RECENT" if days <= 30 else "HISTORICAL"


async def deactivate_fact(db: AsyncSession, user_id: str, item_id: int) -> None:
    item = await db.scalar(select(LifeContextItem).where(
        LifeContextItem.id == item_id, LifeContextItem.user_id == user_id,
        LifeContextItem.status == "active"))
    if item:
        item.status = "inactive"
        await db.commit()


async def retract_fact(db: AsyncSession, user_id: str, domain: str, key: str) -> None:
    """Same "no longer current" treatment as deactivate_fact (status=
    "inactive", dropped from get_active_context) — just triggered by the
    engine itself recognizing a retraction in what the user typed (see
    native_understanding.extract_knowledge's retractions list) rather than
    a UI delete click, so it's looked up by (domain, key) instead of a
    fact id the chat pipeline never has. A no-op when nothing active is on
    record for that key — nothing to retract is not an error."""
    item = await db.scalar(select(LifeContextItem).where(
        LifeContextItem.user_id == user_id, LifeContextItem.domain == domain,
        LifeContextItem.key == key, LifeContextItem.status == "active"))
    if item:
        item.status = "inactive"
        await db.commit()


async def get_active_context(
    db: AsyncSession, user_id: str, domains: list[str] | None = None
) -> dict[str, dict[str, dict]]:
    """{domain: {key: {value, confidence, source, captured_at, last_confirmed_at}}}
    for every currently-active fact, optionally restricted to a set of
    domains — the chat pipeline passes only the domains relevant to the
    detected category (see chat_understanding._CATEGORY_DOMAINS) rather
    than dumping the user's entire life context into every prompt. The
    confidence returned here is the DECAYED one (see effective_confidence),
    since this is what actually reaches the LLM prompt."""
    stmt = select(LifeContextItem).where(LifeContextItem.user_id == user_id, LifeContextItem.status == "active")
    if domains is not None:
        stmt = stmt.where(LifeContextItem.domain.in_(domains))
    result = await db.execute(stmt)
    out: dict[str, dict[str, dict]] = {}
    for row in result.scalars().all():
        out.setdefault(row.domain, {})[row.key] = {
            "id": row.id,
            "value": row.value,
            "confidence": effective_confidence(row.confidence, row.last_confirmed_at),
            "source": row.source,
            "last_confirmed_at": row.last_confirmed_at.isoformat() if row.last_confirmed_at else None,
            "relevance": memory_relevance(row.status, row.last_confirmed_at),
        }
    return out


async def get_active_facts(db: AsyncSession, user_id: str) -> list[LifeContextItem]:
    """Every active fact as raw rows (with `id`) — for the "My Life Twin"
    screen (product spec §14), which needs a real id per fact to let the
    user edit/delete it; get_active_context's grouped-dict shape (no id,
    used for the chat prompt) isn't enough for that."""
    result = await db.execute(
        select(LifeContextItem).where(LifeContextItem.user_id == user_id, LifeContextItem.status == "active")
    )
    return list(result.scalars().all())


async def get_fact_history(db: AsyncSession, user_id: str, domain: str, key: str) -> list[dict]:
    """Every value ever recorded for one (domain, key), oldest first —
    e.g. salary_range over time. Superseded rows are never deleted, only
    marked, so this is a plain chronological query, not a separate table."""
    result = await db.execute(
        select(LifeContextItem)
        .where(LifeContextItem.user_id == user_id, LifeContextItem.domain == domain, LifeContextItem.key == key)
        .order_by(LifeContextItem.captured_at.asc())
    )
    return [
        {"value": r.value, "status": r.status, "captured_at": r.captured_at.isoformat()}
        for r in result.scalars().all()
    ]


async def delete_fact(db: AsyncSession, user_id: str, item_id: int) -> bool:
    """User-initiated removal (the product spec's "the Life Twin belongs to
    the user" — see/correct/delete). Soft-deleted (status="deleted"), not
    row-removed — it disappears from get_active_context exactly like a real
    delete, but the row surviving is what lets the "Correction Rate" metric
    (app.services.metrics_service) count how often the app got something
    wrong enough that the user removed it, instead of losing that signal."""
    result = await db.execute(
        select(LifeContextItem).where(
            LifeContextItem.id == item_id, LifeContextItem.user_id == user_id, LifeContextItem.status == "active"
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return False
    item.status = "deleted"
    await db.commit()
    return True


async def correct_fact(db: AsyncSession, user_id: str, item_id: int, new_value: str) -> LifeContextItem | None:
    """The user editing a remembered value directly (product spec's
    "correct" action, distinct from "remove") — always lands as
    source="user_confirmed"/confidence="high" and goes through the same
    supersede-and-insert history path as upsert_fact, so a correction is
    itself just another entry in that fact's history, not a hidden edit."""
    result = await db.execute(
        select(LifeContextItem).where(
            LifeContextItem.id == item_id, LifeContextItem.user_id == user_id, LifeContextItem.status == "active"
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None
    return await upsert_fact(db, user_id, item.domain, item.key, new_value, "high", "user_confirmed")


async def upsert_decision(
    db: AsyncSession, user_id: str, category: str, context_note: str | None
) -> LifeDecision | None:
    """Creates (or refreshes the context on) the user's one open decision of
    this type — category is a chat classifier category
    (job_change_decision/business_start_decision), mapped to a
    decision_type. Deliberately at most one OPEN decision per type per
    user: re-raising the same kind of decision in a later conversation
    updates the existing row's context rather than spawning duplicates,
    which is what makes "last time we discussed this, you were still
    exploring" possible."""
    decision_type = _DECISION_TYPE_BY_CATEGORY.get(category)
    if decision_type is None:
        return None

    result = await db.execute(
        select(LifeDecision).where(
            LifeDecision.user_id == user_id,
            LifeDecision.decision_type == decision_type,
            LifeDecision.status == "exploring",
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        if context_note:
            existing.context = context_note
        await db.commit()
        return existing

    decision = LifeDecision(user_id=user_id, decision_type=decision_type, context=context_note)
    db.add(decision)
    await db.commit()
    await db.refresh(decision)
    return decision


async def get_open_decisions(db: AsyncSession, user_id: str) -> list[LifeDecision]:
    result = await db.execute(
        select(LifeDecision).where(LifeDecision.user_id == user_id, LifeDecision.status == "exploring")
    )
    return list(result.scalars().all())


# An outcome check-in is only worth asking once the decision has had time to
# actually play out — the product spec's own "60-90 days later" window;
# picking the middle of that range rather than either edge.
_OUTCOME_CHECKIN_DELAY_DAYS = 75


async def mark_decision(
    db: AsyncSession, user_id: str, category: str, status: str, final_choice: str | None
) -> LifeDecision | None:
    """Moves the user's open decision of this type to "decided" (or
    "abandoned") once they've actually stated a real-world choice ("I
    accepted the new job") — see chat_understanding's decision-status
    extraction. Setting decided_at here is what starts the Outcome
    Follow-Up clock (see get_decisions_due_for_outcome_checkin)."""
    decision_type = _DECISION_TYPE_BY_CATEGORY.get(category)
    if decision_type is None:
        return None
    result = await db.execute(
        select(LifeDecision).where(
            LifeDecision.user_id == user_id,
            LifeDecision.decision_type == decision_type,
            LifeDecision.status == "exploring",
        )
    )
    decision = result.scalar_one_or_none()
    if decision is None:
        return None
    decision.status = status
    decision.final_choice = final_choice
    decision.decided_at = datetime.now(timezone.utc)
    await db.commit()
    return decision


async def get_decisions_due_for_outcome_checkin(db: AsyncSession, user_id: str) -> list[LifeDecision]:
    """Decisions marked "decided" long enough ago (see
    _OUTCOME_CHECKIN_DELAY_DAYS) that haven't had an outcome captured yet —
    chat.py surfaces (at most) one of these as a check-in question the next
    time the user opens a brand-new conversation, per the product spec's
    §12. This is a plain query run on an ordinary request, not a scheduled
    background job — see LifeDecision.outcome's docstring for why."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=_OUTCOME_CHECKIN_DELAY_DAYS)
    result = await db.execute(
        select(LifeDecision).where(
            LifeDecision.user_id == user_id,
            LifeDecision.status == "decided",
            LifeDecision.decided_at.is_not(None),
            LifeDecision.decided_at <= cutoff,
            LifeDecision.outcome.is_(None),
        )
    )
    return list(result.scalars().all())


async def record_outcome(db: AsyncSession, user_id: str, decision_id: int, outcome: str) -> LifeDecision | None:
    result = await db.execute(
        select(LifeDecision).where(LifeDecision.id == decision_id, LifeDecision.user_id == user_id)
    )
    decision = result.scalar_one_or_none()
    if decision is None:
        return None
    decision.outcome = outcome
    decision.outcome_captured_at = datetime.now(timezone.utc)
    await db.commit()
    return decision


async def get_all_decisions(db: AsyncSession, user_id: str) -> list[LifeDecision]:
    result = await db.execute(select(LifeDecision).where(LifeDecision.user_id == user_id))
    return list(result.scalars().all())


_VALID_EVENT_TYPES = {
    "new_job", "promotion", "started_business", "engagement", "marriage", "breakup",
    "moved_city", "became_parent", "other",
}


async def add_event(
    db: AsyncSession, user_id: str, event_type: str, description: str, year: int, month: int | None = None
) -> LifeEvent:
    """Life Timeline entry (product spec §10) — a point in time, not a
    current-state fact, so it's never superseded the way LifeContextItem
    facts are; multiple events of the same type (e.g. two promotions) are
    just multiple rows. A rough, obviously-implausible year (before 1900 or
    in the future) is dropped to "other"/current-year territory rather than
    trusted blindly, since this comes from free-text extraction, not a
    date picker."""
    if event_type not in _VALID_EVENT_TYPES:
        event_type = "other"
    current_year = datetime.now(timezone.utc).year
    if year < 1900 or year > current_year:
        year = current_year
    event = LifeEvent(user_id=user_id, event_type=event_type, description=description, year=year, month=month)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def get_timeline(db: AsyncSession, user_id: str) -> list[dict]:
    """Every event, oldest first — grouping by year for display is left to
    the caller (frontend/serializer), this just returns real, sorted rows."""
    result = await db.execute(
        select(LifeEvent).where(LifeEvent.user_id == user_id).order_by(LifeEvent.year.asc(), LifeEvent.month.asc())
    )
    return [
        {"id": e.id, "event_type": e.event_type, "description": e.description, "year": e.year, "month": e.month}
        for e in result.scalars().all()
    ]


async def get_facts_due_for_reconfirmation(db: AsyncSession, user_id: str) -> list[LifeContextItem]:
    """Product spec §13 — Context Decay: an active fact in a domain likely
    to change over time (see _RECONFIRM_DOMAINS) that's gone stale enough
    to have decayed all the way to "low" effective confidence (see
    effective_confidence) is surfaced here, oldest-confirmed first, so
    chat.py can ask a deterministic "is this still true?" question at most
    once per fresh conversation — same "pull on next request" pattern as
    get_decisions_due_for_outcome_checkin, for the same reason (no
    scheduled-job infrastructure exists to push this proactively)."""
    result = await db.execute(
        select(LifeContextItem)
        .where(
            LifeContextItem.user_id == user_id,
            LifeContextItem.status == "active",
            LifeContextItem.domain.in_(_RECONFIRM_DOMAINS),
        )
        .order_by(LifeContextItem.last_confirmed_at.asc())
    )
    return [
        item for item in result.scalars().all()
        if effective_confidence(item.confidence, item.last_confirmed_at) == "low"
    ]
