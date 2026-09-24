"""Coverage for app.services.native_understanding — the provider-free
conversation understanding layer (deterministic intent detection + fact
extraction). See that module's docstring: "Only explicit first-person
assertions become facts. Unsupported language remains unknown and is
clarified, never inferred by a remote model."

Split out of the original combined test_native_intelligence.py so each new
native-engine module has its own dedicated test file, matching the
convention already used for every other service in this codebase."""
import pytest

from app.services.chat_understanding import classify_message
from app.services.interpretation.templates import _detect_categories
from app.services.native_understanding import (
    _capability_refusal, detect_intents, extract_knowledge, is_navigational_reply, is_question,
)


def facts_for(message):
    facts, state, events, deadline, retractions = extract_knowledge(message)
    return {(f.domain, f.key): f.value for f in facts}, state, events


def test_explicit_knowledge_not_questions_hypotheticals_or_other_people():
    facts, state, _ = facts_for("I work as a developer. I want to start an ecommerce business. I already have paying customers.")
    assert facts["career", "occupation"] == "developer"
    assert facts["business", "business_type"] == "ecommerce"
    assert facts["business", "stage"] == "early_revenue"
    assert state.business_state == "running"
    for message in ("What if I am married?", "My friend is a developer.", "I am not married.", "I used to work as a developer."):
        facts, state, _ = facts_for(message)
        assert ("career", "occupation") not in facts
        assert state is None or state.marital_status != "married"


def test_business_retraction_clears_business_state_and_flags_facts_for_retraction():
    """Caught live: "i dont have business it was just an idea" — a direct
    contradiction of an already-stored business.stage="has_customers" fact
    from an earlier turn — extracted nothing at all, so the stale fact kept
    being echoed back verbatim on every later reply even after the user
    said otherwise. extract_knowledge now flags the 3 business facts that
    only mean something if a business is real for retraction (chat.py
    applies life_context_service.retract_fact for each), and resets the
    life-state gate the same way the existing pregnancy negation does."""
    facts, state, events, deadline, retractions = extract_knowledge("i dont have business it was just an idea")
    assert facts == []
    assert state.business_state == "none"
    assert set(retractions) == {
        ("business", "stage"), ("business", "transition_intent"), ("business", "business_type"),
    }


def test_business_retraction_variant_phrasings():
    for message in (
        "i don't have a business",
        "i do not own a business",
        "my business was just an idea",
    ):
        _, state, _, _, retractions = extract_knowledge(message)
        assert state.business_state == "none", message
        assert ("business", "stage") in retractions, message


def test_no_business_retraction_for_an_unrelated_message():
    _, state, _, _, retractions = extract_knowledge("I already have paying customers for my business.")
    assert retractions == []
    assert state.business_state == "running"


async def test_credentials_cannot_enable_remote_understanding(monkeypatch):
    import openai
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: pytest.fail("native understanding called GPT"))
    result = await classify_message([{"role": "user", "content": "I work as a developer."}], "vyasa", 1990, "en")
    assert result.context_updates[0].value == "developer"
    assert result.life_state_update.career_state == "employed"


def test_investment_and_business_are_native_intents():
    assert "investment_decision" in detect_intents("Should I invest now?")
    assert "business" in detect_intents("How is my business looking?")


def test_typo_tolerant_extraction_catches_a_common_misspelling():
    """Regression guard for a real, reproduced bug: "i am alrady married"
    (typo for "already") silently extracted NOTHING before this fix — the
    marital-status regex has zero built-in tolerance for an unrecognized
    filler word, so the already-married reframing gate in
    prediction_service.py never got the fact it needed. Fixed via
    _fuzzy_normalize, reusing templates.py's own proven edit-distance
    tolerance rather than hand-patching this one regex."""
    facts, state, _ = facts_for("I am alrady married")
    assert state.marital_status == "married"
    assert facts["relationships", "relationship_status"] == "married"


def test_typo_tolerant_extraction_still_respects_negation_and_hypotheticals():
    """The normalization pass must not accidentally make a previously-safe
    hypothetical/negation start matching — only individual word spelling is
    corrected, the clause-level guards in extract_knowledge are untouched."""
    facts, state, _ = facts_for("What if I am alrady married?")
    assert ("relationships", "relationship_status") not in facts
    assert state is None or state.marital_status != "married"


def test_family_planning_intent_is_extracted():
    """Regression guard for a real, reproduced bug: "we are thinking about
    family planning" extracted nothing at all — no parallel to the existing
    business.transition_intent pattern existed for the family domain."""
    facts, _, _ = facts_for("Now we are thinking about family planning")
    assert facts["family", "planning_intent"] == "considering family planning"


def test_family_planning_intent_survives_the_exact_transcript_typos():
    """The real message, typos and all — "abaout" (about) and "pallning"
    (planning). Caught live: the first fuzzy-normalize pass fixed
    "pallning" but "about" wasn't yet in the anchor word list, so the
    pattern's required literal "about" still failed to match."""
    facts, _, _ = facts_for("now we are thinking abaout family pallning")
    assert facts["family", "planning_intent"] == "considering family planning"


def test_week_ahead_is_a_real_category_not_a_dead_end():
    """Regression guard: "Mera hafta kaisa rahega?" (how will my week be?)
    matched no category at all before this fix and fell straight to the
    generic clarifying question — no week-scoped intent existed anywhere
    (only "today" and "year_ahead")."""
    assert _detect_categories("mera hafta kaisa rahega") == ["week_ahead"]
    assert _detect_categories("how is my week looking") == ["week_ahead"]


def test_rishta_is_recognized_as_a_relationship_question():
    """Regression guard: "Mera rishta kaisa rahega?" — the Hindi/Hinglish
    word for "relationship" — matched no marriage keyword at all (only the
    English word was recognized anywhere) and fell straight to the generic
    clarifying question, the same class of gap as "hafta"/week_ahead."""
    assert _detect_categories("mera rishta kaisa rahega") == ["marriage"]


def test_im_without_apostrophe_is_recognized_same_as_i_am_or_i_m():
    """Regression guard for a real, reproduced bug: "im married" (no
    apostrophe — an extremely common way "I'm" actually gets typed)
    extracted nothing at all, because every "i am|i'm X" pattern in this
    module requires either the apostrophe or a separate "am"."""
    facts, state, _ = facts_for("im married")
    assert state.marital_status == "married"
    assert facts["relationships", "relationship_status"] == "married"


def test_additional_ways_of_stating_married_status_are_recognized():
    """Regression guard for a real, reproduced bug: a user said they'd
    already told the chat they were married, but the reframe never fired —
    traced to several common real phrasings ("I got married", "a married
    man", Hinglish "shaadi shuda"/"married hu") extracting nothing at all,
    only the single narrow "i am/i'm married" form was recognized."""
    for message in ("I got married", "I am a married man", "married hu", "shaadi shuda hoon", "shaadishuda hoon"):
        facts, state, _ = facts_for(message)
        assert state.marital_status == "married", message
    # Negation must still work correctly against the widened pattern.
    facts, state, _ = facts_for("I am not married")
    assert state.marital_status == "single"
    facts, state, _ = facts_for("what if i got married")
    assert state is None or state.marital_status != "married"


def test_request_framing_is_recognized_as_a_question_not_a_stated_fact():
    """Regression guard for a real, reproduced bug: "I want to ask about my
    relationship" got quoted back to the SAME user as "an earlier related
    conversation" they supposedly needed to update — nonsensical for a
    request that was never a stated fact."""
    assert is_question("I want to ask about my relationship")
    assert is_question("i want to know about my career")
    assert is_question("mujhe janna hai ki career kaisa rahega")


def test_is_navigational_reply_catches_bare_domain_words_and_menu_picks():
    """Regression guard for a real, reproduced bug: a bare one-word reply
    like "relationship" (picking a topic, nothing more) got stored and later
    quoted back as "an earlier related conversation you said" — nonsensical
    for a word that was never a stated fact about the user's life."""
    assert is_navigational_reply("relationship")
    assert is_navigational_reply("career")
    assert is_navigational_reply("2")
    assert not is_navigational_reply("I am already married")
    assert not is_navigational_reply("My relationship has been on my mind a lot lately")
    # Deliberately NOT folded into is_question — conversation_engine.resume()
    # needs is_question to stay False for these exact words so its own
    # pending_domain_clarification gate can resolve them via
    # _resolve_domain_word.
    assert not is_question("relationship")
    assert not is_question("career")


def test_relationship_distress_is_recognized_not_treated_as_a_neutral_status_check():
    """Regression guard for a real, reproduced bug: "main shaadi se dukhi
    hoon" (I am unhappy because of my marriage) — a distress statement, not
    a neutral "tell me about my marriage" ask — got the exact same generic
    reading a plain status check would, completely missing that this is a
    problem the user needs help with. Also covers the exact live typo
    ("shhadi" for "shaadi"), which the fuzzy-normalize pass must fix here
    the same way it already does inside extract_knowledge."""
    assert detect_intents("main shaadi se dukhi hoon") == ["relationship_conflict"]
    assert detect_intents("main shhadi se dukhi hoon") == ["relationship_conflict"]
    assert "relationship_conflict" in detect_intents("I am so unhappy in my marriage")


def test_marrige_typo_corrects_to_the_closer_match_not_the_first_list_match():
    """Regression guard for a real, reproduced bug: "marrige" (typo, missing
    the second "a") corrected to "married" instead of "marriage" — not
    because it was the better match (it's actually farther: distance 2 vs
    1), but purely because "married" sits earlier in the anchor word list
    and also happened to satisfy the fuzzy threshold. _fuzzy_normalize must
    pick the closest match by actual edit distance, never let list order
    silently decide between two real, similar words."""
    assert "relationship_conflict" in detect_intents("but there is a problem in my marrige")


def test_relation_ship_typed_as_two_words_still_resolves():
    """Regression guard for a real, reproduced bug: a real user's message
    literally split the word into two ("I want to ask about relation ship"),
    which the single-token "relationship" keyword can never match since it
    checks whole words — fell straight to the generic clarifying question."""
    assert "marriage" in detect_intents("i want to ask about relation ship")


def test_rishta_does_not_fuzzy_collide_with_the_word_right():
    """Regression guard for a real, reproduced bug introduced while fixing
    the above: "rishta"/"rishte" fuzzy-matched the common English word
    "right" at edit distance 2, so a plain dasha question ("...running RIGHT
    now") wrongly also answered an unrelated relationship question. Fixed by
    making rishta/rishte exact-only, same as the existing dasha/dosha fix."""
    assert _detect_categories("what dasha am i running right now") == ["dasha"]


def test_having_and_been_do_not_fuzzy_collide_with_hiring_and_behen():
    """Regression guard for a real, reproduced bug: a long free-text answer
    to a pending slot question ("We keep having communication problems...
    it has been going on for six months") got wrongly reclassified as a
    career/siblings question mid-conversation — "having" fuzzy-matched the
    career keyword "hiring", and "been" fuzzy-matched "behen" (Hindi for
    sister) — overriding the pending slot it was actually answering. Same
    false-positive class as rishta/right above."""
    assert _detect_categories(
        "we keep having communication problems and it has been going on for six months"
    ) == []


def test_is_question_distinguishes_a_question_from_a_stated_fact():
    assert is_question("What does my kundli say about marriage and partner?")
    assert is_question("kab shaadi hogi")
    assert not is_question("I am already married")
    assert not is_question("My sister is getting married soon.")


def test_relationship_sub_intents_are_distinguished_not_collapsed_to_generic_marriage():
    """Regression guard for the real, reproduced architecture gap: every
    relationship question used to collapse into the single generic
    "marriage" house-7 bucket regardless of what was actually asked — a
    married user asking about spouse bonding got the identical answer a
    single person asking "when will I get married" would."""
    assert "spouse_relationship" in detect_intents("How is my married life with my wife going?")
    assert "relationship_conflict" in detect_intents("We keep having a fight in our marriage")
    assert "family_planning" in detect_intents("We are planning a family")
    # A bare mention still falls back to the generic bucket — only a
    # specific phrasing should resolve to a sub-intent.
    assert detect_intents("I want to ask about my relationship") == ["marriage"]


def test_family_planning_does_not_also_trigger_the_generic_family_topic():
    """Regression guard for a real, reproduced bug: "yes, Family planning"
    matched BOTH the family_planning sub-intent AND the generic bare
    "family" topic (the word "family" is literally a _TOPIC_KEYWORDS
    keyword too) — neither is the other's alias parent, so the existing
    dedup only ever dropped "marriage", leaving both in the final list.
    chat_reply then answered BOTH and concatenated a relationship template
    with an unrelated family template into one reply — traced live via the
    chat_reasoning_trace log showing detected_intent: ["family_planning",
    "family"]."""
    assert detect_intents("yes, Family planning") == ["family_planning"]
    assert detect_intents("We are planning a family") == ["family_planning"]


def test_career_and_finance_sub_intents_are_detected():
    assert "workplace_problem" in detect_intents("I have a conflict with my boss at work")
    assert "career_confusion" in detect_intents("I am confused about my career direction")
    assert "financial_stability" in detect_intents("I want financial stability")


def test_dont_get_along_is_recognized_as_relationship_conflict_with_no_other_keyword():
    """Regression guard for a real, reproduced bug: "We both do not get
    along" has no "fight"/"conflict"/"unhappy" word at all, so it matched
    ZERO categories — not even the generic "marriage" catch-all — and fell
    straight to the fully generic "what do you want to talk about"
    clarifying question, even when this immediately followed an active
    relationship topic. "get along" is also a _TOPIC_KEYWORDS["friends"]
    phrase, so the bare "friends" catch-all must be suppressed here the
    same way family_planning already suppresses bare "family"."""
    for message in ("we both do not get along", "we dont get along", "i dont get along with him", "hum dono nahi bante"):
        assert detect_intents(message) == ["relationship_conflict"]


def test_not_sure_about_career_is_confusion_not_a_timing_question():
    """Regression guard for two real, reproduced bugs in one message: (1)
    "not sure" wasn't recognized as a career_confusion trigger at all (only
    "confused"/"unsure"/"lost" were), so this fell through to the plain
    "career" topic; (2) worse, the word "well" (as in "as well") fuzzy-
    matched the "will i"/"will my" timing-hint phrase at edit-distance 1,
    wrongly making it look like a WHEN-will-my-career-improve timing
    question and returning job-change dates instead of recognizing career
    confusion. Caught live via chat_reasoning_trace showing detected_intent
    ["career_timing"] for this exact message."""
    categories = detect_intents("I am not sure about my career as well")
    assert categories == ["career_confusion"]
    assert "career_timing" not in categories


def test_business_typo_is_still_recognized_by_detect_intents():
    """Regression guard for a real, reproduced bug: "buisness" (a common
    transposition typo) matched none of detect_intents' plain regex checks
    (the decision patterns and the bare "business" catch-all both matched
    against the RAW message, only extract_knowledge's fact extraction used
    the typo-corrected text) — so "I want to switch to buisness" was tagged
    bare "career" only and answered with stale job-change timing content,
    even though the identically-intentioned correctly-spelled message
    resolved fine."""
    assert detect_intents("i want to switch to buisness") == detect_intents("i want to switch to business")
    assert "business" in detect_intents("i want to switch to buisness")


def test_switch_to_business_is_recorded_as_a_transition_fact():
    """Regression guard: the business-transition fact pattern only
    recognized "start/build/launch" verbs, so "I want to switch to
    business" recorded nothing at all — meaning business_state never left
    None/considering, and the bare-career intent-menu gate kept re-firing
    on every later career-related message even after the user had already
    given a clear, specific answer."""
    facts, state, _ = facts_for("I want to switch to business")
    assert facts["business", "transition_intent"] == "start a business"
    assert state.business_state == "considering"


def test_spouse_name_is_extracted():
    """Regression guard for a real gap: nothing extracted a spouse's name at
    all, even though every "you and X" personalized callback needs it."""
    facts, _, _ = facts_for("My wife is Priya and we are doing well")
    assert facts["relationships", "spouse_name"] == "priya"


def test_capability_refusal_declines_child_gender_honestly():
    """Phase 8 — Answer Capability Resolver: an unanswerable question gets an
    honest decline instead of silently falling through to a generic
    fallback answer that pretends the question was addressed."""
    refusal = _capability_refusal("Will my baby be a boy or girl?", "en")
    assert refusal is not None
    assert "can't predict" in refusal.lower()
    assert _capability_refusal("How is my career looking?", "en") is None


def test_is_question_catches_imperative_requests_without_a_question_mark():
    """Regression guard for a real, reproduced bug: "Tell me about my
    marriage prospects" has no "?" and doesn't start with an interrogative,
    so it slipped past is_question and got surfaced as a quoted "situation"
    ("if that has changed") — nonsensical for a request, same as a real
    question."""
    assert is_question("Tell me about my marriage prospects")
    assert is_question("Explain my career timing")
    assert is_question("बताइए मेरी शादी कब होगी")
    assert not is_question("I told my friend about my new job.")
