"""Phase 6 — a single 0-100 "how well does the app actually know this
person" score, built entirely from already-stored Phases 1-5 signals: no
new astrology, no LLM, pure arithmetic aggregation. Its own file (not
tacked onto life_context_service.py) since it aggregates across 4
different services/tables — same reasoning life_pattern_service.py/
important_date_service.py got their own files in Phase 5.

Deliberately no separate "onboarding submitted" bucket: submit_onboarding_
context only ever writes a goals-domain LifeContextItem fact, so a
dedicated bucket for it would double-count exactly what the domains-
covered bucket below already measures.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.important_date import ImportantDate
from app.services import life_context_service, user_service

_DOMAIN_WEIGHT = 50
_LIFE_STATE_WEIGHT = 20
_LIFE_EVENT_WEIGHT = 10
_IMPORTANT_DATE_WEIGHT = 10
_DECISION_WEIGHT = 10
_LIFE_STATE_FIELDS_TOTAL = 3  # marital_status, career_state, business_state


async def get_personalization_score(db: AsyncSession, user_id: str) -> dict:
    context = await life_context_service.get_active_context(db, user_id)
    domains_covered = len(context)
    domains_total = len(life_context_service.VALID_DOMAINS)

    life_state_row = await user_service.get_life_state(db, user_id)
    life_state = user_service.decrypt_life_state(life_state_row) if life_state_row else None
    life_state_fields_set = sum(
        1 for v in (
            (life_state.marital_status if life_state else None),
            (life_state.career_state if life_state else None),
            (life_state.business_state if life_state else None),
        )
        # "none" (e.g. business_state="none", explicitly stated as "no
        # business") is a real known fact for completeness purposes, unlike
        # chat.py's own current_life_state_for_prompt filtering (which
        # drops "none"/0 as "nothing worth mentioning in a prompt") — a
        # different purpose, so only an unset (never-stated) field counts
        # against the score here.
        if v is not None
    )

    timeline = await life_context_service.get_timeline(db, user_id)
    has_life_event = len(timeline) > 0

    decisions = await life_context_service.get_all_decisions(db, user_id)
    has_tracked_decision = len(decisions) > 0

    result = await db.execute(select(func.count()).select_from(ImportantDate).where(ImportantDate.user_id == user_id))
    has_important_date = (result.scalar_one() or 0) > 0

    score = round(
        _DOMAIN_WEIGHT * (domains_covered / domains_total)
        + _LIFE_STATE_WEIGHT * (life_state_fields_set / _LIFE_STATE_FIELDS_TOTAL)
        + (_LIFE_EVENT_WEIGHT if has_life_event else 0)
        + (_IMPORTANT_DATE_WEIGHT if has_important_date else 0)
        + (_DECISION_WEIGHT if has_tracked_decision else 0)
    )

    return {
        "score": score,
        "domains_covered": domains_covered,
        "domains_total": domains_total,
        "life_state_fields_set": life_state_fields_set,
        "life_state_fields_total": _LIFE_STATE_FIELDS_TOTAL,
        "has_life_event": has_life_event,
        "has_important_date": has_important_date,
        "has_tracked_decision": has_tracked_decision,
    }
