"""Life Intelligence health metrics (product spec §20) — deliberately NOT
messages-sent/sessions/astrology-questions-asked, which measure engagement
with the app in general, not whether the Life Context Engine specifically
is doing anything useful. Every metric here is a plain aggregate query
computed on demand (see app/api/v1/admin.py's /admin/metrics), not a
separate tracked/cached rollup — the underlying tables are small enough
that this is cheap, and a live number is more trustworthy than a stale one."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import ChatMessage
from app.db.models.life_context import LifeContextItem, LifeDecision


async def context_depth(db: AsyncSession) -> dict:
    """How many useful confirmed facts do we know, app-wide and on average
    per user who has any — a user with zero facts yet (hasn't chatted
    enough) shouldn't drag the average toward zero and hide that the
    engine works well for users who HAVE engaged."""
    total = await db.scalar(
        select(func.count()).select_from(LifeContextItem).where(LifeContextItem.status == "active")
    )
    users_with_facts = await db.scalar(
        select(func.count(func.distinct(LifeContextItem.user_id))).where(LifeContextItem.status == "active")
    )
    return {
        "total_active_facts": total or 0,
        "users_with_at_least_one_fact": users_with_facts or 0,
        "avg_facts_per_engaged_user": round((total or 0) / users_with_facts, 1) if users_with_facts else 0.0,
    }


async def context_utilization(db: AsyncSession) -> dict:
    """Of every real assistant reply, what fraction actually had personal
    context on the table when it was composed (see ChatMessage.
    used_personalization, set in app/api/v1/chat.py) — not "does
    personalization exist," but "was it actually available for this
    specific answer.\""""
    total_replies = await db.scalar(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.role == "assistant")
    )
    with_context = await db.scalar(
        select(func.count()).select_from(ChatMessage).where(
            ChatMessage.role == "assistant", ChatMessage.used_personalization.is_(True)
        )
    )
    rate = round((with_context or 0) / total_replies, 3) if total_replies else 0.0
    return {"total_assistant_replies": total_replies or 0, "replies_using_context": with_context or 0, "utilization_rate": rate}


async def correction_rate(db: AsyncSession) -> dict:
    """How often the user has to tell us we got their memory wrong —
    every LifeContextItem ever created (any status) vs. how many were
    later explicitly deleted by the user (see life_context_service.
    delete_fact, a soft-delete precisely so this stays countable)."""
    total_ever = await db.scalar(select(func.count()).select_from(LifeContextItem))
    deleted = await db.scalar(
        select(func.count()).select_from(LifeContextItem).where(LifeContextItem.status == "deleted")
    )
    rate = round((deleted or 0) / total_ever, 3) if total_ever else 0.0
    return {"total_facts_ever_recorded": total_ever or 0, "user_deleted": deleted or 0, "correction_rate": rate}


async def return_continuity(db: AsyncSession) -> dict:
    """How often a personalized reply is genuinely reaching back across a
    PAST session, not just using something said earlier in the same live
    conversation — approximated as: of the personalized replies, what
    fraction happened on a calendar day AFTER that user's very first
    message ever. A rough proxy (it doesn't prove the specific fact used
    was from a prior day, just that the user is a returning one), but a
    real, computable one rather than an untracked guess."""
    first_message_by_user = (
        select(ChatMessage.user_id, func.min(ChatMessage.created_at).label("first_at"))
        .group_by(ChatMessage.user_id)
        .subquery()
    )
    personalized = (
        select(ChatMessage.user_id, ChatMessage.created_at)
        .where(ChatMessage.role == "assistant", ChatMessage.used_personalization.is_(True))
        .subquery()
    )
    joined = select(func.count()).select_from(personalized).join(
        first_message_by_user, personalized.c.user_id == first_message_by_user.c.user_id
    ).where(personalized.c.created_at > first_message_by_user.c.first_at + timedelta(hours=20))
    returning_personalized = await db.scalar(joined)
    total_personalized = await db.scalar(select(func.count()).select_from(personalized))
    rate = round((returning_personalized or 0) / total_personalized, 3) if total_personalized else 0.0
    return {
        "personalized_replies": total_personalized or 0,
        "personalized_replies_on_a_later_day": returning_personalized or 0,
        "return_continuity_rate": rate,
    }


async def outcome_capture(db: AsyncSession) -> dict:
    """Of decisions the user actually settled (status="decided" — an
    abandoned decision was never acted on, so it has no real-world outcome
    to report), what fraction eventually got an outcome recorded."""
    decided = await db.scalar(
        select(func.count()).select_from(LifeDecision).where(LifeDecision.status == "decided")
    )
    with_outcome = await db.scalar(
        select(func.count()).select_from(LifeDecision).where(
            LifeDecision.status == "decided", LifeDecision.outcome.is_not(None)
        )
    )
    rate = round((with_outcome or 0) / decided, 3) if decided else 0.0
    return {"decisions_decided": decided or 0, "decisions_with_outcome": with_outcome or 0, "outcome_capture_rate": rate}


async def all_metrics(db: AsyncSession) -> dict:
    return {
        "context_depth": await context_depth(db),
        "context_utilization": await context_utilization(db),
        "correction_rate": await correction_rate(db),
        "return_continuity": await return_continuity(db),
        "outcome_capture": await outcome_capture(db),
    }
