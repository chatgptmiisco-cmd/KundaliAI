"""Consolidated, single-address "current conversation state" facade over
ConversationState.data — see the plan's Phase 2 (personal-astrologer chat
upgrade). Life context (durable facts, app.services.life_context_service)
is completely separate from this: this module only ever describes THIS
conversation's live focus (topic, which decision is active, what's known/
missing for it, answer sufficiency, pending question) — never durable facts
themselves, which continue to live in life_context/LifeState exactly as
before.

Deliberately a thin facade, not a new storage mechanism: most of what
get_focus() surfaces already exists as scattered ConversationState.data keys
(categories, pending, pending_candidates, focus_pending, ...) — this just
gives them one addressable shape. The handful of genuinely new fields
(active_decision, known_for_decision, missing_for_decision, engine_ready) are
DERIVED FRESH from life_context facts + DECISION_SLOTS on every read rather
than stored redundantly — this is what lets a brand-new conversation resume
correctly from durable facts without ever replaying raw chat history."""
from app.services.conversation_engine import DECISION_SLOTS, QUESTIONS, known_slot


def _derive_known_and_missing(category: str | None, facts: dict) -> tuple[dict, list[str]]:
    known: dict = {}
    missing: list[str] = []
    for slot in DECISION_SLOTS.get(category, ()):
        domain, key = QUESTIONS[slot][:2]
        if known_slot(slot, facts):
            known[f"{domain}.{key}"] = (facts.get(domain, {}).get(key) or {}).get("value")
        else:
            missing.append(f"{domain}.{key}")
    return known, missing


def resolve_active_decision(category: str | None, facts: dict) -> str | None:
    """A specific label like "business_start:clothing", not just the bare
    category — this is what lets a "changed my plan" follow-up (Phase 5)
    name the actual prior plan instead of asking a generic re-elicitation
    question. None whenever there's no real decision-type category active."""
    if not category or category not in DECISION_SLOTS:
        return None
    business_type = (facts.get("business", {}).get("business_type") or {}).get("value")
    if category in ("business_start_decision", "business") and business_type:
        return f"business_start:{business_type}"
    return category


def get_focus(state: dict, facts: dict | None = None) -> dict:
    """Read-only, always-fresh view of the conversation's current focus.
    `facts` should be the same active-facts dict the rest of the chat
    pipeline already has on hand (life_context_service.get_active_context);
    omitted only by callers that genuinely have no facts available yet, in
    which case decision-derived fields come back empty rather than stale."""
    facts = facts or {}
    stored = state.get("focus") or {}
    categories = state.get("categories") or []
    category = categories[0] if categories else None
    pending = state.get("pending") or []
    pending_question = None
    if pending:
        slot = pending[0]
        domain, key = QUESTIONS[slot][:2]
        pending_question = {"slot": slot, "domain": domain, "key": key}
    known, missing = _derive_known_and_missing(category, facts)
    return {
        "topic": category,
        "intent": category,
        "sub_intent": stored.get("sub_intent"),
        "active_decision": resolve_active_decision(category, facts),
        "stage": "gathering" if pending_question else stored.get("stage", "ready"),
        "known_for_decision": known,
        "missing_for_decision": missing,
        "previous_question": stored.get("previous_question"),
        "previous_answer": stored.get("previous_answer"),
        "answer_sufficiency": stored.get("answer_sufficiency"),
        "pending_question": pending_question,
        "engine_ready": not pending_question,
    }


def update_focus(state: dict, **kwargs) -> None:
    """Persists only the fields get_focus() can't derive fresh each time
    (sub_intent, previous_question/answer, answer_sufficiency, a stage
    override) — topic/pending/known/missing/active_decision are never
    written here, since they're always recomputed from `categories`/
    `pending`/facts on the next get_focus() call."""
    focus = state.setdefault("focus", {})
    focus.update(kwargs)
