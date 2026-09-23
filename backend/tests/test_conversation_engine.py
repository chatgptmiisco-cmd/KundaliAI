"""Coverage for app.services.conversation_engine — persistent intent
resolution and decision-critical questions (no provider calls). See that
module's docstring, and its `questions_for`/`resume` docstrings for the
exact contracts locked in below.

Split out of the original combined test_native_intelligence.py so each new
native-engine module has its own dedicated test file, matching the
convention already used for every other service in this codebase."""
from app.services.chat_understanding import classify_message
from app.services.conversation_engine import questions_for, resume


def test_questions_are_material_and_do_not_loop():
    state = {"categories": ["job_change_decision"]}
    question = questions_for(["job_change_decision"], {}, {}, state, "en")
    assert "1." in question and "2." in question and "3." in question
    assert state["pending"] == ["reason", "offer", "runway"]
    assert questions_for(["job_change_decision"], {}, {}, state, "en") is None


async def test_numbered_answers_resolve_original_intent():
    state = {"categories": ["job_change_decision"], "pending": ["reason", "offer", "runway"]}
    message = "1. Growth 2. No offer 3. Six months of savings"
    result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
    result = resume(result, message, state, "en")
    assert result.categories == ["job_change_decision"]
    saved = {(f.domain, f.key): f.value for f in result.context_updates}
    assert saved["career", "change_reason"] == "Growth"
    assert saved["money", "savings"] == "Six months of savings"
    assert not result.needs_clarification


async def test_generic_clarification_marks_pending_and_a_domain_word_resolves_it():
    """Regression guard for a real, reproduced bug: the generic "work/
    relationships/money/business/family?" clarifying question had zero
    pending-state tracking, so a one-word reply like "kaam" (Hindi for
    "work") was re-run through full intent detection from scratch — which
    fails, since "kaam" isn't a career keyword anywhere — and got the exact
    same clarifying question repeated back verbatim."""
    state = {}
    vague = await classify_message([{"role": "user", "content": "Mujhe kuch samajhna hai"}], "vyasa", 1990, "en")
    vague = resume(vague, "Mujhe kuch samajhna hai", state, "en")
    assert vague.needs_clarification
    assert state["pending_domain_clarification"] is True

    followup = await classify_message([{"role": "user", "content": "kaam"}], "vyasa", 1990, "en")
    followup = resume(followup, "kaam", state, "en")
    assert followup.categories == ["career"]
    assert not followup.needs_clarification
    assert state["pending_domain_clarification"] is False


async def test_generic_clarification_domain_word_resolves_the_plural_form_too():
    """Regression guard for a real, reproduced bug: a reply of exactly
    "relationships" (plural) matched neither the exact-equals nor the
    startswith-plus-space check in _resolve_domain_word (which only knew
    the singular "relationship"), so the domain-clarification gate silently
    did nothing and the message fell through to full category detection
    with marital status not yet known — a full generic timing answer
    instead of resolving the pending question."""
    state = {}
    vague = await classify_message([{"role": "user", "content": "mujhe kuch samajhna hai"}], "vyasa", 1990, "en")
    vague = resume(vague, "mujhe kuch samajhna hai", state, "en")
    assert state["pending_domain_clarification"] is True

    followup = await classify_message([{"role": "user", "content": "relationships"}], "vyasa", 1990, "en")
    followup = resume(followup, "relationships", state, "en")
    assert followup.categories == ["marriage"]
    assert not followup.needs_clarification


async def test_pending_situation_check_no_is_acknowledged_not_reasked():
    """Regression guard for a real, reproduced bug: replying "no" to "if
    that situation has changed, tell me" fell through to the generic
    clarifying question again instead of being acknowledged."""
    state = {"pending_situation_check": {"quote_id": 1}}
    result = await classify_message([{"role": "user", "content": "no"}], "vyasa", 1990, "en")
    result = resume(result, "no", state, "en")
    assert not result.needs_clarification
    assert result.clarifying_question is None
    assert state["pending_situation_check"] is None


async def test_pending_situation_check_yes_asks_what_changed():
    state = {"pending_situation_check": {"quote_id": 1}}
    result = await classify_message([{"role": "user", "content": "yes"}], "vyasa", 1990, "en")
    result = resume(result, "yes", state, "en")
    assert result.needs_clarification
    assert "changed" in result.clarifying_question.lower()
    assert state["pending_situation_check"] is None


def test_already_married_gate_now_covers_the_bare_relationship_category_too():
    """Regression guard for the real gap behind the failing transcript: the
    already-married clarifying question only ever fired for
    "marriage_timing", so a bare "tell me about my relationship" (category
    "marriage") gave a married user the same single-person house-7 answer
    someone still looking for a partner would get."""
    state = {}
    life_state = {"marital_status": "married"}
    question = questions_for(["marriage"], {}, life_state, state, "en")
    assert question is not None
    assert "already married" in question.lower()
    # An unmarried user asking the same bare question gets no such gate.
    state2 = {}
    assert questions_for(["marriage"], {}, {"marital_status": "single"}, state2, "en") is None
    # A sub-intent that's already specific (spouse_relationship etc.) is
    # never re-clarified — detect_intents already disambiguated it.
    state3 = {}
    assert questions_for(["spouse_relationship"], {}, life_state, state3, "en") is None


async def test_marriage_menu_is_personalized_with_the_spouse_name_and_known_facts():
    """Stage 3 — instead of a fixed generic clarifying question, the
    already-married gate now builds a numbered menu of genuinely different
    angles, naming the spouse by name when known and only offering "family
    planning" as an option when that's actually a known fact."""
    state = {}
    life_state = {"marital_status": "married"}
    facts = {"relationships": {"spouse_name": {"value": "priya"}}, "family": {"planning_intent": {"value": "considering family planning"}}}
    question = questions_for(["marriage"], facts, life_state, state, "en")
    assert "Priya" in question
    assert "family planning" in question.lower()
    assert "1." in question and "2." in question
    menu = state["pending_intent_menu"]
    assert menu["gate"] == "marriage"
    assert "family_planning" in menu["options"]

    # Without the planning_intent fact, "family planning" isn't offered as
    # an option at all — never a guessed angle.
    state2 = {}
    question2 = questions_for(["marriage"], {}, life_state, state2, "en")
    assert "family planning" not in question2.lower()


async def test_marriage_menu_numbered_pick_resolves_to_the_specific_sub_intent():
    state = {
        "categories": ["marriage"],
        "pending_intent_menu": {
            "gate": "marriage", "base_category": "marriage",
            "options": ["spouse_relationship", "relationship_conflict", "family_planning", "marriage"],
        },
    }
    message = "3"
    result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
    result = resume(result, message, state, "en")
    assert result.categories == ["family_planning"]
    assert state["marriage_clarified"] is True
    assert state["pending_intent_menu"] is None


async def test_marriage_menu_free_text_pick_also_resolves():
    """A reply that itself names a specific angle should route there
    directly instead of requiring a bare number."""
    state = {
        "categories": ["marriage"],
        "pending_intent_menu": {
            "gate": "marriage", "base_category": "marriage",
            "options": ["spouse_relationship", "relationship_conflict", "family_planning", "marriage"],
        },
    }
    message = "family planning"
    result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
    result = resume(result, message, state, "en")
    assert "family_planning" in result.categories
    assert state["marriage_clarified"] is True


async def test_marriage_menu_vague_reply_falls_back_to_base_category():
    state = {
        "categories": ["marriage"],
        "pending_intent_menu": {"gate": "marriage", "base_category": "marriage", "options": ["spouse_relationship", "marriage"]},
    }
    message = "just tell me generally"
    result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
    result = resume(result, message, state, "en")
    assert result.categories == ["marriage"]
    assert state["marriage_clarified"] is True


def test_career_menu_gates_a_bare_career_ask_when_nothing_is_known():
    """Stage 3 — a bare "Mera career kaisa rahega?" with genuinely nothing
    known (no occupation, no business, no employment state) now asks what
    to focus on instead of guessing a generic answer."""
    state = {}
    question = questions_for(["career"], {}, {}, state, "en")
    assert question is not None
    assert state["pending_intent_menu"]["gate"] == "career"
    # Once ANYTHING is known, the gate is skipped entirely.
    state2 = {}
    facts = {"career": {"occupation": {"value": "developer"}}}
    assert questions_for(["career"], facts, {}, state2, "en") is None
    # And once already clarified this conversation, it's never re-asked.
    state3 = {"career_clarified": True}
    assert questions_for(["career"], {}, {}, state3, "en") is None


async def test_career_menu_numbered_pick_routes_into_an_existing_decision_flow():
    """Picking "changing your job" from the career menu should route into
    job_change_decision, which then naturally asks ITS OWN decision-critical
    questions (reason/offer/runway) on the very next call — no separate
    plumbing needed, this chains through the existing DECISION_SLOTS."""
    state = {
        "categories": ["career"],
        "pending_intent_menu": {
            "gate": "career", "base_category": "career",
            "options": ["career", "job_change_decision", "career_promotion_timing", "business_start_decision"],
        },
    }
    message = "2"
    result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
    result = resume(result, message, state, "en")
    assert result.categories == ["job_change_decision"]
    assert state["career_clarified"] is True
    follow_up = questions_for(result.categories, {}, {}, state, "en")
    assert follow_up is not None
    assert state["pending"] == ["reason", "offer", "runway"]


def test_week_menu_gates_the_first_week_ahead_ask_then_remembers():
    state = {}
    question = questions_for(["week_ahead"], {}, {}, state, "en")
    assert question is not None
    assert state["pending_intent_menu"]["gate"] == "week"
    state["week_clarified"] = True
    assert questions_for(["week_ahead"], {}, {}, state, "en") is None


def test_relationship_conflict_asks_what_the_concern_is_before_answering():
    """Regression guard for a real, reproduced bug: a distress/conflict
    message ("main shaadi se dukhi hoon") went straight to the generic
    astrology reading — a real astrologer asks what's actually happening
    first. Reuses the existing DECISION_SLOTS mechanism (concern_type),
    exactly like the 6 named decisions already do."""
    state = {}
    question = questions_for(["relationship_conflict"], {}, {}, state, "en")
    assert question is not None
    assert "communication" in question.lower()
    assert state["pending"] == ["concern_type"]
    # Once the concern is known, it's never asked again.
    facts = {"relationships": {"concern_type": {"value": "we keep having the same argument", "confidence": "high"}}}
    assert questions_for(["relationship_conflict"], facts, {}, {}, "en") is None


async def test_a_short_topic_word_sent_again_reuses_the_recent_topic_not_the_generic_fallback():
    """Regression guard for a real, reproduced bug: "fights" — one word,
    itself one of the concern_type question's own offered options — sent
    as a FRESH message (the slot it originally answered had already been
    resolved, so nothing was pending) fell through every branch and landed
    on the fully generic "what do you want to talk about" reply, discarding
    an obviously-still-relevant topic just because the message was short
    and contained none of the specific continuation words ("that"/"same"/
    etc.) the old branch required."""
    state = {"categories": ["relationship_conflict"], "pending": []}
    result = await classify_message([{"role": "user", "content": "fights"}], "vyasa", 1990, "en")
    result = resume(result, "fights", state, "en")
    assert result.categories == ["relationship_conflict"]
    assert not result.needs_clarification


async def test_short_reply_does_not_reuse_topic_when_no_recent_topic_exists():
    """The widened branch only fires when there's something to continue —
    an empty conversation still gets the generic clarifying question for a
    short, otherwise-unclassifiable message."""
    state = {}
    result = await classify_message([{"role": "user", "content": "fights"}], "vyasa", 1990, "en")
    result = resume(result, "fights", state, "en")
    assert result.needs_clarification
