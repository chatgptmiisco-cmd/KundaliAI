"""Phase 7 — adaptive multi-session onboarding: "what's the single most
useful thing to ask this user next," computed purely from data already on
record (no new tables, no LLM here — only the EXISTING extract_onboarding_
context call, unchanged, is involved once the user actually answers). Two
triggers, both reusing Phases 1-6's own signals:

1. Life-event-driven: the most recently REPORTED LifeEvent (not the oldest-
   happened one get_timeline orders by) whose event_type maps to one of the
   8 onboarding topics, when that topic's Life Context domain still has
   zero coverage — the same domain-coverage signal Phase 6's completeness
   score already uses.
2. Time-based fallback: once the account is old enough to have had a fair
   chance at (1) or ordinary chat use, the first still-uncovered topic.

Re-suggesting the same topic every time until it's actually answered
(which naturally covers the domain and stops the suggestion) needs no
dismiss-tracking — same reasoning every pull-based signal in Phases 1-5
already relies on.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.life_context import LifeEvent
from app.services import life_context_service

# Give the life-event trigger and ordinary chat use a head start before the
# time-based fallback starts nudging.
_MIN_ACCOUNT_AGE_DAYS = 3

# Onboarding topic slug -> Life Context domain (see life_context_service.
# VALID_DOMAINS) — "identity" has no mapped topic at all, deliberately:
# none of the 8 onboarding topics fits it, so it's never suggested here
# (still counted separately by Phase 6's score).
_TOPIC_DOMAIN: dict[str, str] = {
    "career": "career", "business": "business", "relationships": "relationships",
    "marriage": "relationships", "money": "money", "family": "family",
    "personal_direction": "goals", "other": "preferences",
}

# LifeEvent.event_type -> onboarding topic slug. moved_city/other are
# deliberately unmapped — no single onboarding topic fits either well.
_EVENT_TYPE_TOPIC: dict[str, str] = {
    "new_job": "career", "promotion": "career", "started_business": "business",
    "marriage": "marriage", "engagement": "marriage", "breakup": "relationships",
    "became_parent": "family",
}


async def get_next_onboarding_topic(
    db: AsyncSession, user_id: str, account_created_at: datetime
) -> dict | None:
    context = await life_context_service.get_active_context(db, user_id)
    covered_domains = set(context.keys())

    result = await db.execute(
        select(LifeEvent).where(LifeEvent.user_id == user_id).order_by(LifeEvent.id.desc()).limit(1)
    )
    latest_event = result.scalar_one_or_none()
    if latest_event is not None:
        topic = _EVENT_TYPE_TOPIC.get(latest_event.event_type)
        if topic is not None and _TOPIC_DOMAIN[topic] not in covered_domains:
            return {"topic": topic, "reason": "life_event"}

    # Some DB drivers (e.g. the test suite's SQLite) hand back a naive
    # datetime even for a DateTime(timezone=True) column — assume UTC
    # rather than let the subtraction below raise.
    if account_created_at.tzinfo is None:
        account_created_at = account_created_at.replace(tzinfo=timezone.utc)
    account_age = datetime.now(timezone.utc) - account_created_at
    if account_age >= timedelta(days=_MIN_ACCOUNT_AGE_DAYS):
        for topic, domain in _TOPIC_DOMAIN.items():
            if domain not in covered_domains:
                return {"topic": topic, "reason": "time_based"}

    return None
