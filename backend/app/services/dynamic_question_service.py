"""Durable question+answer memory and anonymized cross-user learning — see
the personal-astrologer chat upgrade plan's Phase 6. Two things live here,
mirroring life_context_service's own conventions:

  1. DynamicQuestionLog — every question the chat pipeline asked (GPT-
     generated or the deterministic DECISION_SLOTS fallback) plus its
     answer, per user. Distinct from ConversationState.data, which only
     ever tracks a slot ID/position for the CURRENT conversation's live
     pending question, never question text or answers.
  2. QuestionPatternStats — anonymized, aggregated (category, domain, key)
     counts with NO user_id and NO question/answer text, ever. Incremented
     alongside every DynamicQuestionLog write."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dynamic_question_log import DynamicQuestionLog
from app.db.models.question_pattern_stats import QuestionPatternStats


async def _bump_pattern_stats(db: AsyncSession, category: str, target_domain: str, target_key: str, **counters: int) -> None:
    result = await db.execute(
        select(QuestionPatternStats).where(
            QuestionPatternStats.category == category,
            QuestionPatternStats.target_domain == target_domain,
            QuestionPatternStats.target_key == target_key,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = QuestionPatternStats(category=category, target_domain=target_domain, target_key=target_key)
        db.add(row)
        await db.flush()
    for field, amount in counters.items():
        setattr(row, field, getattr(row, field) + amount)
    await db.commit()


async def log_question(
    db: AsyncSession, user_id: str, rishi_id: str, category: str, sub_intent: str | None,
    question_text: str, target_domain: str, target_key: str, is_novel_concept: bool, source: str,
) -> DynamicQuestionLog:
    """Records a question as asked. Any earlier "current" row for the exact
    same (user, target_domain, target_key) is marked "historical" first —
    mirrors LifeContextItem's own active/superseded convention, so a later
    re-ask of the same concept never leaves two "current" rows contradicting
    each other."""
    result = await db.execute(
        select(DynamicQuestionLog).where(
            DynamicQuestionLog.user_id == user_id,
            DynamicQuestionLog.target_domain == target_domain,
            DynamicQuestionLog.target_key == target_key,
            DynamicQuestionLog.status == "current",
        )
    )
    for row in result.scalars():
        row.status = "historical"

    entry = DynamicQuestionLog(
        user_id=user_id, rishi_id=rishi_id or "", category=category, sub_intent=sub_intent,
        question_text=question_text, target_domain=target_domain, target_key=target_key,
        is_novel_concept=is_novel_concept, source=source, status="current",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    await _bump_pattern_stats(db, category, target_domain, target_key, times_asked=1)
    return entry


async def record_answer(
    db: AsyncSession, question_id: int, answer_text: str, normalized_value: str | None, confidence: str | None,
) -> DynamicQuestionLog | None:
    """Attaches an answer to a previously logged question. Returns None if
    the question_id doesn't exist (caller treats that as a no-op, never an
    error — this is a best-effort learning signal, not load-bearing for the
    actual reply)."""
    entry = await db.get(DynamicQuestionLog, question_id)
    if entry is None:
        return None
    entry.answer_text = answer_text
    entry.normalized_value = normalized_value
    entry.confidence = confidence
    entry.answered_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(entry)
    await _bump_pattern_stats(db, entry.category, entry.target_domain, entry.target_key, times_answered=1)
    return entry


async def record_usefulness(
    db: AsyncSession, category: str, target_domain: str, target_key: str,
    answer_usable: bool = False, resolved_missing_information: bool = False, answer_ready_after: bool = False,
) -> None:
    """Anonymized-only usefulness signals (QuestionPatternStats has no
    user_id/text columns to attach these to a specific answer) — called
    whenever the caller can cheaply tell one of these happened (e.g. the GPT
    interpretation layer's fact-preservation check referenced the answer, or
    assess_and_generate_question's answer_ready flipped true right after)."""
    counters = {
        "times_answer_usable": int(answer_usable),
        "times_resolved_missing_information": int(resolved_missing_information),
        "times_answer_ready_after": int(answer_ready_after),
    }
    counters = {k: v for k, v in counters.items() if v}
    if counters:
        await _bump_pattern_stats(db, category, target_domain, target_key, **counters)


async def get_recent_for_user(db: AsyncSession, user_id: str, limit: int = 5) -> list[dict]:
    """Feeds assess_and_generate_question's `prior_questions_text` — a short
    summary of this user's own prior dynamic Q&A so GPT doesn't regenerate
    something already asked. Most-recent first."""
    result = await db.execute(
        select(DynamicQuestionLog)
        .where(DynamicQuestionLog.user_id == user_id)
        .order_by(DynamicQuestionLog.asked_at.desc())
        .limit(limit)
    )
    return [
        {
            "category": row.category, "sub_intent": row.sub_intent, "question_text": row.question_text,
            "target_domain": row.target_domain, "target_key": row.target_key,
            "answer_text": row.answer_text, "status": row.status,
        }
        for row in result.scalars()
    ]
