"""Coverage for app.services.native_response — personal_context() and
practical_framing(), the two pieces of compose() that turn computed facts
into personalized prose before the astrology template itself runs.

No dedicated test file existed for this module before Stage 2 (it was only
exercised indirectly via test_native_chat_integration.py) — added now to
match the per-module convention used everywhere else in this codebase,
since Stage 2 added real new behavior here (goals-as-list, named decision
facts) worth locking in directly."""
from app.services.native_response import personal_context, practical_framing


def _fact(value, source="user_stated", confidence="high"):
    return {"value": value, "source": source, "confidence": confidence}


def test_personal_context_lists_recent_distinct_goals_not_just_the_latest():
    """Stage 2 — goals as a list: a "top_goal" fact only ever holds the
    LATEST value (upsert_fact supersedes on change), so surfacing just that
    would lose every earlier goal the moment a new one replaces it. Reuses
    Phase 7's existing fact-correction history instead of a new key scheme."""
    context = {
        "life_context": {"career": {"occupation": _fact("developer")}},
        "goal_history": [
            {"value": "save money", "status": "superseded", "captured_at": "2026-01-01T00:00:00+00:00"},
            {"value": "get promoted", "status": "superseded", "captured_at": "2026-02-01T00:00:00+00:00"},
            {"value": "get promoted", "status": "active", "captured_at": "2026-02-15T00:00:00+00:00"},
        ],
    }
    result = personal_context(context, "en")
    assert "save money" in result
    assert "get promoted" in result
    # The repeated re-statement of "get promoted" is deduped, not listed twice.
    assert result.count("get promoted") == 1


def test_personal_context_without_goal_history_omits_the_goals_line():
    context = {"life_context": {"career": {"occupation": _fact("developer")}}, "goal_history": []}
    result = personal_context(context, "en")
    assert "goal" not in result.lower()


def test_personal_context_title_cases_spouse_name_for_display():
    context = {"life_context": {"relationships": {"spouse_name": _fact("priya")}}}
    result = personal_context(context, "en")
    assert "Priya" in result
    assert "priya:" not in result.lower().replace("your spouse: priya", "")


def test_practical_framing_names_the_actual_collected_job_change_facts():
    """Phase 14 — the interpretation should reference the SPECIFIC facts
    already collected via conversation_engine's DECISION_SLOTS, not only a
    generic caveat that never repeats back what the user actually said."""
    context = {
        "detected_categories": ["job_change_decision"],
        "life_context": {
            "career": {"change_reason": _fact("burnout"), "alternative_opportunity": _fact("a concrete offer in hand")},
            "money": {"savings": _fact("four months")},
        },
    }
    result = practical_framing(context, "en")
    assert "burnout" in result
    assert "a concrete offer in hand" in result
    assert "four months" in result


def test_practical_framing_omits_named_facts_sentence_when_nothing_collected_yet():
    context = {"detected_categories": ["job_change_decision"], "life_context": {}}
    result = practical_framing(context, "en")
    assert "Specifically" not in result


def test_personal_context_skips_relationship_status_when_a_reframe_will_state_it():
    """Regression guard for a real, reproduced complaint: "your relationship
    status: married" appeared as a flat fact line immediately before
    _context_lead_in's own "Since you're already married, I won't treat
    this as marriage timing..." reframe — the same fact stated twice, once
    as a debug-sounding line and once naturally. Suppressed only for
    categories where that reframe actually fires; a category with no
    reframe still gets the plain fact list."""
    context = {
        "detected_categories": ["marriage"],
        "life_state": {"marital_status": "married"},
        "life_context": {"relationships": {"relationship_status": _fact("married")}},
    }
    result = personal_context(context, "en")
    assert "relationship status" not in result.lower()

    # A category with no marital reframe (e.g. plain career) still shows it.
    other_context = {**context, "detected_categories": ["career"]}
    other_result = personal_context(other_context, "en")
    assert "relationship status" in other_result.lower()

    # Not married — nothing to reframe around, so the fact still shows.
    single_context = {**context, "life_state": {"marital_status": "single"}}
    single_result = personal_context(single_context, "en")
    assert "relationship status" in single_result.lower()


async def test_compose_quote_callback_is_not_shown_twice_as_hard_when_a_reframe_already_personalizes():
    """Regression guard for a real, reproduced bug introduced by the fix
    above: suppressing personal_context's redundant "relationship status:
    married" line made `personal` empty MORE often for exactly the
    categories with a marital reframe — which made compose()'s "only show
    the quote-callback if NOT already personalized" gate let it through
    MORE, not less, stacking a second "in an earlier conversation you
    said..." callback right after a reply that already opened with "Since
    you're already married...". A category whose own reframe already
    personalizes the reply must count as personalized here too."""
    from app.services.native_response import compose

    context = {
        "detected_categories": ["marriage"],
        "life_state": {"marital_status": "married"},
        "life_context": {"relationships": {"relationship_status": _fact("married")}},
        "retrieved_history": [{"source": "user_quote", "text": "I already told you I'm married", "id": 1}],
        "house_verdict": {7: "Your relationships may have both good and hard moments."},
    }
    reply = await compose([{"role": "user", "content": "tell me about my relationship"}], context, "en")
    assert "in an earlier related conversation" not in reply.lower()
