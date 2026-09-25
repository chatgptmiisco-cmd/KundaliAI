"""Coverage for app.services.conversation_state — the consolidated,
single-address "current conversation focus" facade over
ConversationState.data (see the plan's Phase 2). No provider calls."""
from app.services.conversation_state import get_focus, resolve_active_decision, update_focus


def test_get_focus_derives_topic_and_pending_question_from_existing_state_keys():
    state = {"categories": ["business_start_decision"], "pending": ["transition_mode"]}
    focus = get_focus(state)
    assert focus["topic"] == "business_start_decision"
    assert focus["intent"] == "business_start_decision"
    assert focus["pending_question"] == {"slot": "transition_mode", "domain": "business", "key": "transition_mode"}
    assert focus["stage"] == "gathering"
    assert focus["engine_ready"] is False


def test_get_focus_reports_engine_ready_once_nothing_is_pending():
    state = {"categories": ["career"], "pending": []}
    focus = get_focus(state)
    assert focus["pending_question"] is None
    assert focus["engine_ready"] is True
    assert focus["stage"] == "ready"


def test_known_and_missing_for_decision_derive_fresh_from_facts_not_stored_state():
    state = {"categories": ["business_start_decision"], "pending": []}
    facts = {"business": {"goal": {"value": "clothing", "confidence": "high"}}}
    focus = get_focus(state, facts)
    assert "business.goal" in focus["known_for_decision"]
    assert focus["known_for_decision"]["business.goal"] == "clothing"
    assert "business.funding" in focus["missing_for_decision"]
    # A brand new conversation (fresh `state`, same durable facts) derives
    # the identical known/missing split — nothing was replayed from history.
    fresh_state = {"categories": ["business_start_decision"], "pending": []}
    fresh_focus = get_focus(fresh_state, facts)
    assert fresh_focus["known_for_decision"] == focus["known_for_decision"]
    assert fresh_focus["missing_for_decision"] == focus["missing_for_decision"]


def test_resolve_active_decision_names_the_specific_business_type_when_known():
    facts = {"business": {"business_type": {"value": "clothing", "confidence": "high"}}}
    assert resolve_active_decision("business_start_decision", facts) == "business_start:clothing"
    assert resolve_active_decision("business_start_decision", {}) == "business_start_decision"
    assert resolve_active_decision("relationship_conflict", {}) == "relationship_conflict"
    assert resolve_active_decision(None, {}) is None
    assert resolve_active_decision("week_ahead", {}) is None


def test_update_focus_round_trips_only_the_genuinely_new_fields():
    state: dict = {"categories": ["business_start_decision"], "pending": []}
    update_focus(state, sub_intent="business_category_suitability", answer_sufficiency=40)
    focus = get_focus(state)
    assert focus["sub_intent"] == "business_category_suitability"
    assert focus["answer_sufficiency"] == 40
    # Persisted only under state["focus"] — never duplicated at top level.
    assert state["focus"] == {"sub_intent": "business_category_suitability", "answer_sufficiency": 40}
