"""Coverage for app.services.native_response — personal_context() and
practical_framing(), the two pieces of compose() that turn computed facts
into personalized prose before the astrology template itself runs.

No dedicated test file existed for this module before Stage 2 (it was only
exercised indirectly via test_native_chat_integration.py) — added now to
match the per-module convention used everywhere else in this codebase,
since Stage 2 added real new behavior here (goals-as-list, named decision
facts) worth locking in directly."""
from app.services.native_response import _as_clause, personal_context, practical_framing


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


def test_personal_context_does_not_repeat_a_fact_already_shown_this_conversation():
    """Direct product feedback: "your work: Job in IT sector" got restated
    on EVERY career-related turn for a whole conversation, not just the
    turn it was first established. `shown_facts` (persisted turn to turn
    by chat.py via ConversationState) tracks which facts have already been
    surfaced at least once; a fact whose exact "domain:key:value" identity
    is already there is skipped on later turns."""
    context = {
        "life_context": {"career": {"occupation": _fact("developer")}},
        "shown_facts": {"career:occupation:developer"},
    }
    result = personal_context(context, "en")
    assert result == ""


def test_personal_context_shows_a_fact_once_and_records_it_as_shown():
    """The FIRST time a fact appears, it still shows — and shown_facts (a
    plain set, mutated in place) picks up its identity so the NEXT call
    with the same set knows to suppress it."""
    shown_facts = set()
    context = {"life_context": {"career": {"occupation": _fact("developer")}}, "shown_facts": shown_facts}
    first = personal_context(context, "en")
    assert "developer" in first
    assert "career:occupation:developer" in shown_facts

    second = personal_context(context, "en")
    assert second == ""


def test_personal_context_without_shown_facts_key_always_shows_every_call():
    """None (the default when a caller doesn't pass shown_facts at all —
    e.g. a one-shot call with no conversation state) disables the dedup
    entirely, preserving the original always-show behavior."""
    context = {"life_context": {"career": {"occupation": _fact("developer")}}}
    assert "developer" in personal_context(context, "en")
    assert "developer" in personal_context(context, "en")


def test_personal_context_never_leaks_a_raw_internal_slot_key_as_a_label():
    """Caught live, reproducing the exact leak this whole function exists to
    prevent: DECISION_SLOTS writes free-text answers under internal slot
    keys ("goal", "funding" — see conversation_engine.QUESTIONS' business_
    goal/funding entries, both stored under domain "business") that were
    never given a friendly label. The old fallback (`key.replace("_", " ")`)
    rendered them anyway — "goal: clothing and yes i have customers,;
    funding: i have some savings..." shown verbatim to the user. Those
    facts get real synthesis elsewhere (_named_facts_sentence); an
    unlabeled key here is now skipped, never raw-dumped."""
    context = {
        "life_context": {
            "business": {
                "stage": _fact("has_customers"),
                "goal": _fact("clothing and yes i have customers,"),
                "funding": _fact("i have some savings and i will do this business parttime"),
            },
        },
    }
    result = personal_context(context, "en")
    assert "goal:" not in result.lower()
    assert "funding:" not in result.lower()
    # A key that DOES have an authored clause template still renders normally.
    assert "your business already has customers" in result.lower()


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
    # "burnout" is capitalized when it opens the synthesized sentence
    # (see _named_facts_sentence) — a cosmetic difference from the raw
    # stated value, checked case-insensitively here for that reason.
    assert "burnout" in result.lower()
    assert "a concrete offer in hand" in result
    assert "four months" in result
    # The fixed, identical-for-everyone decision-framework paragraph this
    # function used to always prepend ("Compare staying, accepting a
    # concrete offer, and resigning without one... A supportive chart
    # window is not a job offer or a replacement for income") is gone —
    # per direct, explicit feedback, this internal reasoning must never
    # appear in the user-facing response by default.
    assert "supportive chart window" not in result.lower()
    assert "compare staying" not in result.lower()


def test_practical_framing_synthesizes_bare_business_the_same_as_business_start_decision():
    """conversation_engine.DECISION_SLOTS registers a bare "business" (e.g.
    mid a career conversation) as an alias of business_start_decision,
    reusing the exact same business_goal/funding slots — but
    _named_facts_sentence only recognized "business_start_decision",
    leaving "business" turns with no synthesized sentence at all. Caught
    live: with no synthesis, practical_framing produced nothing, and the
    raw goal/funding facts (now correctly suppressed by personal_context)
    had nowhere else to surface — the reply lost the person's own answer
    entirely instead of stating it naturally."""
    context = {
        "detected_categories": ["business"],
        "life_context": {"business": {"goal": _fact("clothing"), "funding": _fact("my own savings")}},
    }
    result = practical_framing(context, "en")
    assert "clothing" in result
    assert "my own savings" in result


def test_personal_context_suppresses_the_redundant_career_transition_intent_clause():
    """Caught live: "I want to switch to business" writes career.
    transition_intent="business" AND business.transition_intent="start a
    business" — two DIFFERENT literal values for the same underlying
    concept, so the value/clause-level dedupe can't catch it. Rendered back
    to back this read "You've mentioned that you're considering business and
    you're considering start a business" — an awkward near-duplicate.
    business's own (more specific) clause should be the only one shown."""
    context = {
        "life_context": {
            "career": {"transition_intent": _fact("business")},
            "business": {"transition_intent": _fact("start a business")},
        },
    }
    result = personal_context(context, "en")
    assert result.count("considering") == 1
    assert "start a business" in result


def test_practical_framing_synthesizes_business_type_stated_as_a_plain_assertion_too():
    """Caught live (Scenario E, personal-astrologer chat upgrade plan): "I
    want to start a clothing business" extracts to business.business_type,
    a DIFFERENT key from business.goal (only ever written by answering the
    business_goal QUESTION). conversation_engine.known_slot already treats
    the two as equivalent for gating (the question is correctly never
    re-asked) — but _named_facts_sentence read "goal" only, so the type was
    silently never named back to the user even though it was genuinely
    known. Must fall back to business_type when goal itself is unset."""
    context = {
        "detected_categories": ["business"],
        "life_context": {"business": {"business_type": _fact("clothing"), "funding": _fact("my own savings")}},
    }
    result = practical_framing(context, "en")
    assert "clothing" in result
    assert "my own savings" in result


def test_practical_framing_names_a_suited_industry_once_business_questions_are_answered():
    """Direct product ask: once business_start_decision's own goal/funding
    questions are both answered, name a SPECIFIC suited industry from the
    chart (classical planet significations) instead of only restating what
    the person already said back to them — "it's up to you which business
    you continue, but astrologically you have a good hand for X"."""
    context = {
        "detected_categories": ["business_start_decision"],
        "life_context": {"business": {"goal": _fact("clothing"), "funding": _fact("my own savings")}},
        "strongest_planet_code": "Ma",
    }
    result = practical_framing(context, "en")
    assert "clothing" in result
    assert "engineering, electricals, machinery" in result
    assert "up to you" in result.lower()


def test_practical_framing_names_the_suited_industry_only_once_per_conversation():
    """Direct follow-up feedback: the industry suggestion re-stated on
    EVERY later business-related turn once goal+funding were known — "add
    it for the situation, not every chat." Its own shown_facts gate (a
    synthetic identity, separate from the goal/funding restatement above,
    which is left as-is) suppresses it on the second call."""
    shown_facts = set()
    context = {
        "detected_categories": ["business_start_decision"],
        "life_context": {"business": {"goal": _fact("clothing"), "funding": _fact("my own savings")}},
        "strongest_planet_code": "Ma",
        "shown_facts": shown_facts,
    }
    first = practical_framing(context, "en")
    assert "engineering, electricals, machinery" in first

    second = practical_framing(context, "en")
    assert "engineering, electricals, machinery" not in second
    # The combination sentence itself (goal/funding) is untouched by this
    # gate — only the industry clause is suppressed.
    assert "clothing" in second


def test_practical_framing_industry_suggestion_is_omitted_without_a_strongest_planet():
    """No astrology data available (strongest_planet_code missing/None) —
    the sentence must never guess or fall back to a generic industry."""
    context = {
        "detected_categories": ["business_start_decision"],
        "life_context": {"business": {"goal": _fact("clothing"), "funding": _fact("my own savings")}},
    }
    result = practical_framing(context, "en")
    assert "clothing" in result
    assert "up to you" not in result.lower()


def test_practical_framing_never_states_the_fixed_decision_framework_disclaimer():
    """Same removal, covering every other decision type the old `rules`
    dict used to hold a fixed paragraph for — none of them should produce
    output here at all once no specific fact has been collected yet,
    confirming the fixed disclaimer paragraph isn't firing as a fallback."""
    for category in (
        "business_start_decision", "relocation_decision", "house_purchase_decision",
        "marriage_decision", "investment_decision",
    ):
        assert practical_framing({"detected_categories": [category], "life_context": {}}, "en") == ""


def test_as_clause_strips_leading_self_reference_for_natural_interpolation():
    """Regression guard for a real, reproduced bug: a DECISION_SLOTS answer
    is free text in the user's own first-person voice ("I already have
    another offer") — interpolating it as-is into a sentence that supplies
    its OWN "you already have {value}" framing produced an awkward double
    self-reference ("you already have I already have another offer").
    Display-only: the stored fact value itself is never touched, and a
    value with no recognizable leading phrase passes through unchanged."""
    assert _as_clause("I already have another offer") == "another offer"
    assert _as_clause("I have another offer") == "another offer"
    assert _as_clause("Yes, I have savings") == "savings"
    assert _as_clause("a concrete offer in hand") == "a concrete offer in hand"


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
    assert "you are married" in other_result.lower()

    # Not married — nothing to reframe around, so the fact still shows.
    single_context = {**context, "life_state": {"marital_status": "single"}}
    single_result = personal_context(single_context, "en")
    assert "you are married" in single_result.lower()


async def test_compose_caches_its_personal_context_result_for_chat_py_to_reuse():
    """chat.py calls personal_context() a SECOND time after compose()
    returns, to decide whether to gate its own quote-callback (see
    chat.py's `_personal_context_result` usage). With shown_facts' dedup
    mutating state on every call, a literal second call would always see
    everything as already-shown and report empty — wrongly signaling "not
    personalized" even when compose() genuinely did personalize the reply.
    compose() must cache the real result on the context for reuse instead."""
    from app.services.native_response import compose

    context = {
        "detected_categories": ["career"],
        "life_context": {"career": {"occupation": _fact("developer")}},
        "shown_facts": set(),
        "house_verdict": {10: "Your career may have both good and hard phases."},
    }
    await compose([{"role": "user", "content": "career"}], context, "en")
    assert context["_personal_context_result"]
    assert "developer" in context["_personal_context_result"]


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


async def test_compose_quote_callback_is_not_shown_twice_when_the_business_reframe_already_personalizes():
    """Same bug as the marital-reframe regression above, caught live for
    the OTHER _context_lead_in reframe: a "career" turn with a known
    business fact got BOTH "Kyunki aap apne business par dhyaan de rahe
    hain..." (the business-focused reframe) AND, right after it, "Pichli
    baat-cheet mein aapne kaha tha: '1 clothings and yes i have
    costumenrs...'" — the quote-callback verbatim-repeating the SAME old
    business message the reframe had just referenced. _has_marital_reframe
    only ever covered the marital case; the business one needs the same
    "already personalized, don't also quote-back" suppression."""
    from app.services.native_response import compose

    context = {
        "detected_categories": ["career"],
        "life_state": {"business_state": "running"},
        "life_context": {"business": {"business_type": _fact("clothing")}},
        "retrieved_history": [{"source": "user_quote", "text": "1 clothings and yes i have costumenrs", "id": 1}],
        "house_verdict": {10: "Your career may have both good and hard phases."},
    }
    reply = await compose([{"role": "user", "content": "career"}], context, "en")
    assert "in an earlier related conversation" not in reply.lower()


async def test_compose_never_states_the_decision_missing_caveat():
    """Regression guard for a real, explicit feedback item: "The practical
    details are still incomplete, so treat this as conditional guidance
    rather than a recommendation to act" was appended to EVERY incomplete
    decision reply, regardless of the person — internal reasoning about the
    engine's own confidence, not something a human astrologer says out
    loud by default. Removed; the still-missing slots are already visible
    via the numbered follow-up question when there is one."""
    from app.services.native_response import compose

    context = {
        "detected_categories": ["job_change_decision"],
        "life_state": {}, "life_context": {},
        "decision_missing": True,
        "house_verdict": {10: "Your career may have both good phases and hard phases."},
    }
    reply = await compose([{"role": "user", "content": "should I change jobs"}], context, "en")
    assert "conditional guidance" not in reply.lower()
    assert "not a recommendation" not in reply.lower()
