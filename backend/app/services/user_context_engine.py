"""Intent-scoped view over existing authoritative memory. No duplicate life store."""
from sqlalchemy import select

from app.db.models.life_context import LifeEvent, LifeDecision
from app.db.models.prediction_feedback import PredictionFeedback
from app.db.models.prediction_query_log import PredictionQueryLog
from app.db.models.conversation_state import ConversationState
from app.services import life_context_service, user_service
from app.services.chat_understanding import relevant_domains

EVENT_DOMAINS = {
    "new_job": "career", "promotion": "career", "started_business": "business",
    "marriage": "relationships", "engagement": "relationships", "breakup": "relationships",
    "became_parent": "family", "moved_city": "preferences",
}


def filter_facts(facts, categories):
    """Related responsibilities matter for decisions; unrelated family details do not."""
    domains = relevant_domains(categories)
    out = {d: dict(v) for d, v in facts.items() if d in domains}
    if any(c in categories for c in ("job_change_decision", "business_start_decision", "investment_decision")):
        if "family" in out:
            out["family"] = {k: v for k, v in out["family"].items() if any(s in k for s in ("responsibil", "depend", "expense", "commitment"))}
        out.pop("relationships", None)
    return {d: v for d, v in out.items() if v}


async def retrieve(db, user_id, categories):
    domains = relevant_domains(categories)
    facts = filter_facts(await life_context_service.get_active_context(db, user_id, domains), categories)
    # Stage 2 — "goals as a list": rather than a new key scheme (which would
    # break known_slot()'s existing "top_goal" alias lookups and the
    # onboarding_slot mapping), reuse the fact-correction history Phase 7
    # already builds for free — every DISTINCT goal ever stated is already
    # preserved there (superseded, never deleted) the moment a new one
    # replaces it. personal_context() surfaces the recent distinct ones.
    goal_history = await life_context_service.get_fact_history(db, user_id, "goals", "top_goal") if "goals" in domains else []
    event_types = [k for k, v in EVENT_DOMAINS.items() if v in domains]
    events = list((await db.scalars(select(LifeEvent).where(
        LifeEvent.user_id == user_id, LifeEvent.event_type.in_(event_types)
    ).order_by(LifeEvent.year.desc(), LifeEvent.id.desc()).limit(5))).all()) if event_types else []
    feedback = list((await db.scalars(select(PredictionFeedback).where(
        PredictionFeedback.user_id == user_id, PredictionFeedback.feedback.is_not(None)
    ).order_by(PredictionFeedback.id.desc()).limit(30))).all())
    feedback = [f for f in feedback if set(f.domain.split("+")) & set(domains)][:3]
    intents = set(categories) | {c.removesuffix("_timing").removesuffix("_decision") for c in categories}
    predictions = list((await db.scalars(select(PredictionQueryLog).where(
        PredictionQueryLog.user_id == user_id, PredictionQueryLog.intent.in_(intents)
    ).order_by(PredictionQueryLog.id.desc()).limit(3))).all())
    decisions = await life_context_service.get_open_decisions(db, user_id)
    decisions = [d for d in decisions if life_context_service.CATEGORY_BY_DECISION_TYPE.get(d.decision_type) in categories]
    row = await user_service.get_life_state(db, user_id)
    return {
        "life_context": facts,
        "life_state": user_service.decrypt_life_state(row).model_dump(mode="json") if row else {},
        "validated_events": [{"event_type": e.event_type, "description": e.description, "year": e.year, "month": e.month, "source": "user_reported"} for e in events],
        "prediction_feedback": [{"verdict": f.feedback, "detail": f.confirmed_detail, "year": f.window_start.year, "domain": f.domain} for f in feedback],
        "previous_predictions": [{"intent": p.intent, "result": p.result_summary} for p in predictions],
        "open_decisions": [{"decision_type": d.decision_type, "context": d.context, "status": d.status} for d in decisions],
        "goal_history": goal_history,
    }


async def life_model(db, user):
    """Owner-facing projection; chat continues to use only intent-scoped views."""
    profile = await user_service.get_user_profile(db, user)
    facts = await life_context_service.get_active_context(db, user.id)
    states = list((await db.scalars(select(ConversationState).where(ConversationState.user_id == user.id))).all())
    decisions = list((await db.scalars(select(LifeDecision).where(LifeDecision.user_id == user.id))).all())
    feedback = list((await db.scalars(select(PredictionFeedback).where(PredictionFeedback.user_id == user.id))).all())
    predictions = list((await db.scalars(select(PredictionQueryLog).where(
        PredictionQueryLog.user_id == user.id).order_by(PredictionQueryLog.id.desc()).limit(20))).all())
    return {
        "identity": profile.model_dump(mode="json"),
        "astrology": {"source": "existing chart and prediction engine", "chart_endpoint": "/api/v1/chart/d1"},
        "career": facts.get("career", {}), "business": facts.get("business", {}),
        "relationship": facts.get("relationships", {}), "family": facts.get("family", {}),
        "finance": facts.get("money", {}), "goals": facts.get("goals", {}),
        "user_preferences": facts.get("preferences", {}),
        "life_events": await life_context_service.get_timeline(db, user.id),
        "decisions": [{"type": d.decision_type, "status": d.status, "context": d.context} for d in decisions],
        "conversation_context": [{"rishi_id": s.rishi_id, **s.data} for s in states],
        "prediction_feedback": [{"domain": f.domain, "verdict": f.feedback, "detail": f.confirmed_detail,
                                 "window_start": f.window_start.isoformat(), "window_end": f.window_end.isoformat()} for f in feedback],
        "recent_predictions": [{"intent": p.intent, "result": p.result_summary, "created_at": p.created_at.isoformat()} for p in predictions],
    }
