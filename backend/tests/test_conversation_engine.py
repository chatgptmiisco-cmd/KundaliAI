"""Coverage for app.services.conversation_engine — persistent intent
resolution and decision-critical questions (no provider calls). See that
module's docstring, and its `questions_for`/`resume` docstrings for the
exact contracts locked in below.

Split out of the original combined test_native_intelligence.py so each new
native-engine module has its own dedicated test file, matching the
convention already used for every other service in this codebase."""
from datetime import datetime, timedelta, timezone

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


async def test_numbered_answers_without_a_period_still_resolve_correctly():
    """Regression guard for a real, reproduced bug: a numbered reply typed
    WITHOUT a period/paren after each digit ("1 clothing and yes i have
    customers, 2 i have some savings and i'll do this business parttime")
    matched neither the strict "1." form nor the single-slot fallback
    (there were 2 pending slots, not 1) — so NOTHING bound through this
    mechanism, and native_understanding.extract_knowledge's own unrelated
    regexes were left to parse the raw sentence on their own, producing a
    garbled fact (one regex's capture running straight through into the
    SECOND numbered item's text). The looser fallback must bind each slot
    to its own numbered segment instead."""
    state = {"categories": ["business_start_decision"], "pending": ["business_goal", "funding"]}
    message = "1 clothing and yes i have customers, 2 i have some savings and i'll do this business parttime"
    result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
    result = resume(result, message, state, "en")
    saved = {(f.domain, f.key): f.value for f in result.context_updates}
    assert saved["business", "goal"] == "clothing and yes i have customers,"
    assert "some savings" in saved["business", "funding"]
    # Nothing from the SECOND numbered item ever leaks into the first slot's
    # value, or vice versa — the exact shape of the original bug.
    assert "savings" not in saved["business", "goal"]


async def test_business_retraction_clears_pending_business_slots_so_the_next_topic_isnt_swallowed():
    """Caught live: after "I don't have a business, it was just an idea",
    the business_goal/funding slots were still `pending` from an earlier
    turn — so the VERY NEXT bare topic word ("career") got silently bound
    as a free-text answer to one of those now-irrelevant questions
    ("You're thinking career, funded by business...") instead of being
    read as a topic change. The retraction message itself must clear those
    stale business slots (and the business category) on the SAME turn."""
    state = {"categories": ["business", "career"], "pending": ["business_goal", "funding"]}
    message = "i dont have business it was just an idea"
    result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
    assert ("business", "stage") in result.retracted_facts
    result = resume(result, message, state, "en")
    saved = {(f.domain, f.key): f.value for f in result.context_updates}
    # Nothing bound to the retracted business slots from this message.
    assert ("business", "goal") not in saved
    assert ("business", "funding") not in saved
    assert state["pending"] == []
    assert "business" not in state["categories"]
    assert "career" in state["categories"]

    # The NEXT turn's bare topic word is read as a topic change again, not
    # swallowed as a stale slot answer.
    next_message = "career"
    next_result = await classify_message([{"role": "user", "content": next_message}], "vyasa", 1990, "en")
    next_result = resume(next_result, next_message, state, "en")
    next_saved = {(f.domain, f.key): f.value for f in next_result.context_updates}
    assert ("business", "goal") not in next_saved


def test_single_stray_digit_does_not_trigger_the_loose_numbered_fallback():
    """The loose fallback only fires when EVERY slot number the question
    actually asked for (1 through len(pending)) is present as its own bare
    marker — an ordinary sentence that happens to contain a digit ("I have
    2 kids and stress is the reason") must never be misread as a numbered
    list and split apart."""
    from app.services.conversation_engine import resume as _resume
    from app.services.chat_understanding import ChatUnderstanding

    state = {"categories": ["job_change_decision"], "pending": ["reason", "offer", "runway"]}
    message = "I have 2 kids and stress is the reason"
    understanding = ChatUnderstanding(categories=["job_change_decision"])
    result = _resume(understanding, message, state, "en")
    saved = {(f.domain, f.key): f.value for f in result.context_updates}
    # Single-slot-style fallback doesn't apply either (3 slots pending), so
    # nothing should bind from this ambiguous sentence at all.
    assert not saved


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


async def test_pending_concern_situation_check_no_routes_to_relationship_conflict():
    """Regression guard for a real, reproduced bug: a bare "relationship"
    mention months after "fights" was mentioned silently reused (or
    silently ignored) that old concern with no acknowledgment either way —
    your own words: "is it the same or a different issue." Confirming "no,
    unchanged" must route THIS turn's answer to relationship_conflict (so
    the real concern-grounded content renders, not the generic married-life
    reading) and refresh the fact so it isn't asked about again for a day."""
    state = {"pending_situation_check": {"stale_fact": {
        "domain": "relationships", "key": "concern_type", "value": "frequent fights or arguments",
        "route_category": "relationship_conflict",
    }}}
    result = await classify_message([{"role": "user", "content": "no"}], "vyasa", 1990, "en")
    result = resume(result, "no", state, "en")
    assert not result.needs_clarification
    assert result.categories == ["relationship_conflict"]
    saved = {(f.domain, f.key): f.value for f in result.context_updates}
    assert saved["relationships", "concern_type"] == "frequent fights or arguments"
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




def test_marriage_gate_skipped_once_clarified_leaves_relationship_conflict_free_to_ask_its_own_follow_up():
    """marriage_clarified only silences the marriage-menu gate above —
    relationship_conflict's own concern-menu/DECISION_SLOTS mechanism
    (concern_pattern/concern_goal) is unrelated and still asks normally.
    (The stale-concern "is that still relevant?" reconfirm this file used
    to test here was removed from conversation_engine.py — see
    test_question_strategy.py, which now owns that behavior via
    question_strategy.relevance_question/resolve_focus.)"""
    state = {"marriage_clarified": True}
    life_state = {"marital_status": "married"}
    facts = {"relationships": {"concern_type": {"value": "frequent fights or arguments", "confidence": "high"}}}
    assert questions_for(["marriage"], facts, life_state, state, "en") is None
    state2 = {"marriage_clarified": True}
    follow_up = questions_for(["relationship_conflict"], facts, life_state, state2, "en")
    assert follow_up is not None and "still what" not in follow_up.lower()


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


def test_career_menu_is_skipped_when_business_is_already_the_specific_answer():
    """Regression guard for a real, reproduced bug: "I want to switch to
    business" resolves to categories ["business", "career"] — "business"
    already IS the specific, disambiguated answer the career gate exists to
    obtain — but the gate only ever checked career_known/facts, so it fired
    anyway and re-asked "what do you want to focus on?" with "starting a
    business" literally offered as one of the options the user had just
    already picked in plain words. The career MENU must never re-fire here;
    a genuine business-transition follow-up (business_goal/funding, DECISION_
    SLOTS["business"]) is expected instead — the old gap was skipping
    straight to an answer with zero context, not "no question at all"."""
    state = {}
    question = questions_for(["business", "career"], {}, {}, state, "en")
    assert question is not None
    assert "focus on" not in question.lower()
    assert "pending_intent_menu" not in state
    # Once business_goal/funding are both known, there's nothing left to ask.
    facts = {"business": {"business_type": {"value": "ecommerce", "confidence": "high"}, "funding_plan": {"value": "savings", "confidence": "high"}}}
    assert questions_for(["business", "career"], facts, {}, {}, "en") is None
    # The gate still protects a genuinely bare "career" ask with nothing known.
    state2 = {}
    assert questions_for(["career"], {}, {}, state2, "en") is not None


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


def test_money_menu_gates_a_bare_money_ask_when_nothing_is_known():
    """Same philosophy as the career menu, applied to money — caught live,
    user's own explicit request: "money ke perspective se aap kya samajhna
    chahte hain?" instead of guessing income vs. savings vs. business income
    vs. financial pressure."""
    state = {}
    question = questions_for(["money"], {}, {}, state, "en")
    assert question is not None
    assert state["pending_intent_menu"]["gate"] == "money"
    # Once anything financial is known, the gate is skipped entirely.
    state2 = {}
    facts = {"money": {"savings": {"value": "6 months", "confidence": "high"}}}
    assert questions_for(["money"], facts, {}, state2, "en") is None
    # And once already clarified this conversation, it's never re-asked.
    state3 = {"money_clarified": True}
    assert questions_for(["money"], {}, {}, state3, "en") is None


async def test_money_menu_numbered_pick_routes_into_an_existing_category():
    state = {
        "categories": ["money"],
        "pending_intent_menu": {
            "gate": "money", "base_category": "money",
            "options": ["wealth_timing", "investment_decision", "business", "financial_stability", "money"],
        },
    }
    message = "2"
    result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
    result = resume(result, message, state, "en")
    assert result.categories == ["investment_decision"]
    assert state["money_clarified"] is True


def test_family_menu_gates_a_bare_family_ask_when_nothing_is_known():
    """Same philosophy as the career/money menus, applied to family."""
    state = {}
    question = questions_for(["family"], {}, {}, state, "en")
    assert question is not None
    assert state["pending_intent_menu"]["gate"] == "family"
    state2 = {}
    facts = {"family": {"planning_intent": {"value": "considering family planning", "confidence": "high"}}}
    assert questions_for(["family"], facts, {}, state2, "en") is None
    state3 = {"family_clarified": True}
    assert questions_for(["family"], {}, {}, state3, "en") is None


async def test_family_menu_numbered_pick_routes_into_an_existing_category():
    state = {
        "categories": ["family"],
        "pending_intent_menu": {
            "gate": "family", "base_category": "family",
            "options": ["marriage", "family_planning", "family"],
        },
    }
    message = "2"
    result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
    result = resume(result, message, state, "en")
    assert result.categories == ["family_planning"]
    assert state["family_clarified"] is True


async def test_stale_fact_shaped_pending_situation_check_still_resolves_generically():
    """conversation_engine.questions_for() no longer produces a "stale_fact"
    -shaped pending_situation_check itself (that reconfirm now lives in
    app.services.question_strategy — see test_question_strategy.py), but
    resume() still knows how to resolve one generically if anything sets
    it, since it's a plain, reusable state shape, not special-cased to a
    single caller."""
    state = {"pending_situation_check": {"stale_fact": {
        "domain": "business", "key": "goal", "value": "steel and sanitary products",
        "route_category": "business",
    }}}
    result = await classify_message([{"role": "user", "content": "no"}], "vyasa", 1990, "en")
    result = resume(result, "no", state, "en")
    assert not result.needs_clarification
    assert result.categories == ["business"]
    saved = {(f.domain, f.key): f.value for f in result.context_updates}
    assert saved["business", "goal"] == "steel and sanitary products"
    assert state["pending_situation_check"] is None


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
    first. concern_type is now a numbered pick (_relationship_concern_menu)
    rather than a free-text DECISION_SLOTS question, gated the same way as
    marriage/career/week's menus (see the next test); a further,
    genuinely new follow-up (concern_pattern/concern_goal) still runs
    through the ordinary DECISION_SLOTS mechanism once concern_type is
    known, exactly like the 6 named decisions already do."""
    state = {}
    question = questions_for(["relationship_conflict"], {}, {}, state, "en")
    assert question is not None
    assert "communication" in question.lower()
    assert state["pending_concern_menu"] is not None
    # Once the concern is known, the follow-up (pattern/goal) is asked next —
    # not the same menu again, and not a jump straight to the chart reading.
    facts = {"relationships": {"concern_type": {"value": "we keep having the same argument", "confidence": "high"}}}
    follow_up = questions_for(["relationship_conflict"], facts, {}, {}, "en")
    assert follow_up is not None
    assert "concern" not in follow_up.lower() or "recurring" in follow_up.lower()
    # Once concern_type, concern_pattern, and concern_goal are ALL known,
    # there's nothing left to ask.
    facts_complete = {"relationships": {
        "concern_type": {"value": "we keep having the same argument", "confidence": "high"},
        "concern_pattern": {"value": "same topic every time", "confidence": "high"},
        "concern_goal": {"value": "understand why", "confidence": "high"},
    }}
    assert questions_for(["relationship_conflict"], facts_complete, {}, {}, "en") is None


async def test_relationship_concern_menu_numbered_pick_sets_the_concern_fact():
    """A numbered pick on the concern menu resolves to the matching canned
    label as a real context_update — not a category switch, unlike
    marriage/career/week's intent menus, since this menu answers a fact,
    not which topic to talk about."""
    state = {"categories": ["relationship_conflict"], "pending_concern_menu": {"options": [
        "frequent fights or arguments", "communication problems", "trust issues",
        "emotional distance", "family interference", "something else",
    ]}}
    message = "1"
    result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
    result = resume(result, message, state, "en")
    assert result.categories == ["relationship_conflict"]
    saved = {(f.domain, f.key): f.value for f in result.context_updates}
    assert saved["relationships", "concern_type"] == "frequent fights or arguments"
    assert state["pending_concern_menu"] is None


async def test_relationship_concern_menu_free_text_pick_is_stored_verbatim():
    """A free-text reply to the concern menu (not a bare number) is honored
    as-is, exactly like the old single free-text concern_type question did —
    caught live as a real risk: a reply like "money issues all the time"
    must not be misread by the generic domain-word fallback as switching
    topic to "money" instead of answering the menu."""
    state = {"categories": ["relationship_conflict"], "pending_concern_menu": {"options": [
        "frequent fights or arguments", "communication problems", "trust issues",
        "emotional distance", "family interference", "something else",
    ]}}
    message = "money issues all the time"
    result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
    result = resume(result, message, state, "en")
    saved = {(f.domain, f.key): f.value for f in result.context_updates}
    assert saved["relationships", "concern_type"] == "money issues all the time"
    assert result.categories == ["relationship_conflict"]


def test_career_confusion_asks_what_the_problem_and_direction_are_before_answering():
    """Regression guard for a real, reproduced bug: "I am not sure about my
    career" went straight to a generic chart reading with zero context —
    the same gap relationship_conflict's concern menu closes for
    relationships. Reuses the ordinary DECISION_SLOTS mechanism, exactly
    like the 6 named decisions and relationship_conflict already do."""
    state = {}
    question = questions_for(["career_confusion"], {}, {}, state, "en")
    assert question is not None
    assert "career" in question.lower()
    assert set(state["pending"]) == {"career_problem", "career_direction"}
    # Once both are known, there's nothing left to ask.
    facts = {"career": {"main_concern": {"value": "not growing fast enough", "confidence": "high"},
                         "transition_intent": {"value": "considering business", "confidence": "high"}}}
    assert questions_for(["career_confusion"], facts, {}, {}, "en") is None


def test_career_confusion_does_not_re_ask_what_job_change_decision_already_answered():
    """career_confusion and job_change_decision share fact keys both ways
    (see known_slot's aliases) — caught live: answering job_change_decision's
    "reason"/"offer" slots first, then later saying "I'm not sure about my
    career", must not ask the same two things again under new slot names."""
    facts = {"career": {"change_reason": {"value": "money", "confidence": "high"},
                         "job_offer": {"value": "no offer yet", "confidence": "high"}}}
    assert questions_for(["career_confusion"], facts, {}, {}, "en") is None


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


async def test_short_reply_with_filler_words_still_reuses_the_recent_topic():
    """Regression guard for a real, reproduced bug: "but is there any
    solution" and "I have changed my plan" both fell through to the fully
    generic "what do you want to talk about" reply — same underlying bug
    as "fights" above. The topic-continuation check no longer counts words
    at all (see the next test) — ANY message with no independently-
    detected category continues the active topic — so these pass trivially
    now, kept here as the original reproduction cases."""
    state = {"categories": ["relationship_conflict"]}
    result = await classify_message([{"role": "user", "content": "but is there any solution"}], "vyasa", 1990, "en")
    result = resume(result, "but is there any solution", state, "en")
    assert result.categories == ["relationship_conflict"]
    assert not result.needs_clarification

    state2 = {"categories": ["business"]}
    result2 = await classify_message([{"role": "user", "content": "I have changed my plan"}], "vyasa", 1990, "en")
    result2 = resume(result2, "I have changed my plan", state2, "en")
    assert result2.categories == ["business"]
    assert not result2.needs_clarification


async def test_bare_dasha_question_defers_to_a_more_specific_active_topic():
    """Regression guard for a real, reproduced bug: "when will be the right
    time?" asked right after establishing a business decision independently
    matches detect_intents' generic, topic-agnostic "dasha" pattern (no
    domain word of its own) — resetting the active topic to a bare dasha
    reading instead of being understood as asking about THAT business's
    timing. Treated as no signal when a different, more specific topic is
    already active; a genuine bare dasha question with nothing else active
    is unaffected."""
    state = {"categories": ["business_start_decision", "business", "career"]}
    result = await classify_message([{"role": "user", "content": "when will be the right time?"}], "vyasa", 1990, "en")
    result = resume(result, "when will be the right time?", state, "en")
    assert result.categories == ["business_start_decision", "business", "career"]

    # A genuine, standalone dasha question with nothing else active still
    # resolves to dasha normally.
    state2 = {}
    result2 = await classify_message([{"role": "user", "content": "when will be the right time?"}], "vyasa", 1990, "en")
    result2 = resume(result2, "when will be the right time?", state2, "en")
    assert result2.categories == ["dasha"]


async def test_a_genuine_question_with_no_independent_category_also_continues_the_topic():
    """Regression guard for a real, reproduced bug (direct, explicit
    feedback with named examples): "can you tell me time?", "what about
    timing?", "any solution?" and a full sentence — "Will clothing work
    for me or should I look for some other options?" — are all genuine
    QUESTIONS with zero independent category signal of their own. The
    length- and question-based restrictions this branch used to have are
    gone entirely: a category-less message inherits the active topic
    regardless of length or phrasing, since an EXPLICIT topic change is
    exactly what a detected category (`direct`) already signals — this is
    what stops it from ever misfiring on a real new topic."""
    for message in (
        "can you tell me time?",
        "what about timing?",
        "any solution?",
        "Will clothing work for me or should I look for some other options?",
    ):
        state = {"categories": ["business_start_decision"]}
        result = await classify_message([{"role": "user", "content": message}], "vyasa", 1990, "en")
        result = resume(result, message, state, "en")
        assert result.categories == ["business_start_decision"], message
        assert not result.needs_clarification, message


async def test_work_now_resolves_the_domain_clarification_to_career():
    """Regression guard for a real, reproduced bug: the generic clarifying
    question literally offers "work" as one of its own five option words
    ("work, relationships, money, business, or family?"), but _DOMAIN_WORDS
    didn't recognize "work" as the career domain — so replying with that
    exact word fell through instead of resolving to career."""
    state = {"pending_domain_clarification": True}
    result = await classify_message([{"role": "user", "content": "work"}], "vyasa", 1990, "en")
    result = resume(result, "work", state, "en")
    assert result.categories == ["career"]
    assert not result.needs_clarification


async def test_unresolved_domain_clarification_reply_does_not_hijack_a_stale_topic():
    """Regression guard for a real, reproduced bug: a one-word reply to
    "what do you want to talk about?" that _resolve_domain_word can't
    recognize fell through all the way to the short-message topic-
    continuation branch, which then silently reused a STALE topic left
    over in state["categories"] from a much earlier, unrelated
    conversation (state has no expiry) — e.g. answering a fresh "work"-ish
    reply with old relationship_conflict content about fights. An
    unresolved domain-clarification reply must re-ask, never guess."""
    state = {"pending_domain_clarification": True, "categories": ["relationship_conflict"]}
    result = await classify_message([{"role": "user", "content": "xyz"}], "vyasa", 1990, "en")
    result = resume(result, "xyz", state, "en")
    assert result.needs_clarification
    assert result.categories != ["relationship_conflict"]


async def test_short_reply_does_not_reuse_topic_when_no_recent_topic_exists():
    """The widened branch only fires when there's something to continue —
    an empty conversation still gets the generic clarifying question for a
    short, otherwise-unclassifiable message."""
    state = {}
    result = await classify_message([{"role": "user", "content": "fights"}], "vyasa", 1990, "en")
    result = resume(result, "fights", state, "en")
    assert result.needs_clarification
