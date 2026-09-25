"""Coverage for app.services.chat_gpt_mediator — deliberately does NOT mock
or simulate any OpenAI/GPT response (per explicit instruction: no GPT usage
in tests, mocked or otherwise). What's tested instead is everything that's
real, deterministic logic with no provider involved at all: the
polarity/fact-token safety checks these functions gate on, and that each
function correctly never constructs a provider client when disabled or
running engine_only. The actual provider round-trip is exercised only by
live, manual verification (see the plan file), never by the automated suite."""
import pytest

from app.services.chat_gpt_mediator import (
    _KNOWN_CATEGORIES, _date_expressed, _fact_tokens, _interpretation_facts_preserved,
    _interpretation_has_no_fabricated_facts, _polarity_signature, _valid_assessment, _values_present,
    answer_unmapped, assess_and_generate_question, build_facts_to_preserve, build_priority_context,
    classify_unmapped_intent, compose_final_reply, normalize_input,
)


async def test_normalize_input_returns_message_unchanged_when_disabled():
    assert await normalize_input("elation ship", "en") == "elation ship"


async def test_classify_unmapped_intent_returns_none_when_disabled():
    assert await classify_unmapped_intent("is there any solution", ["relationship_conflict"], "en") is None


async def test_classify_unmapped_intent_skips_the_provider_entirely_when_no_api_key(monkeypatch):
    import openai
    from app.core.config import Settings

    monkeypatch.setattr(
        "app.services.chat_gpt_mediator.get_settings",
        lambda: Settings(chat_gpt_mediator_enabled=True, openai_api_key=""),
    )
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: pytest.fail("provider must not run"))
    assert await classify_unmapped_intent("is there any solution", [], "en") is None


async def test_answer_unmapped_returns_none_when_disabled():
    assert await answer_unmapped("just wanted to say thanks", "en") is None


async def test_answer_unmapped_skips_the_provider_entirely_when_no_api_key(monkeypatch):
    import openai
    from app.core.config import Settings

    monkeypatch.setattr(
        "app.services.chat_gpt_mediator.get_settings",
        lambda: Settings(chat_gpt_mediator_enabled=True, openai_api_key=""),
    )
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: pytest.fail("provider must not run"))
    assert await answer_unmapped("just wanted to say thanks", "en") is None


async def test_assess_and_generate_question_returns_none_when_disabled():
    assert await assess_and_generate_question("business", "ctx", "", "i want to switch to business", "", "en") is None


async def test_assess_and_generate_question_skips_the_provider_entirely_when_no_api_key(monkeypatch):
    import openai
    from app.core.config import Settings

    monkeypatch.setattr(
        "app.services.chat_gpt_mediator.get_settings",
        lambda: Settings(chat_dynamic_questions_enabled=True, openai_api_key=""),
    )
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: pytest.fail("provider must not run"))
    assert await assess_and_generate_question("business", "ctx", "", "i want to switch to business", "", "en") is None


def test_valid_assessment_requires_bounded_domain_and_snake_case_key_when_a_question_is_required():
    base = {"answer_ready": False, "confidence": 30, "missing_information": ["existing_customers"], "next_question_required": True}
    assert _valid_assessment({**base, "question": "Do you have customers?", "target_domain": "business", "target_key": "existing_customers"})
    # Domain outside VALID_DOMAINS -> rejected, regardless of how plausible the rest looks.
    assert not _valid_assessment({**base, "question": "Do you have customers?", "target_domain": "astrology", "target_key": "existing_customers"})
    # target_key must be snake_case, not free text or camelCase.
    assert not _valid_assessment({**base, "question": "Do you have customers?", "target_domain": "business", "target_key": "Existing Customers"})
    # A missing question when one is required -> rejected.
    assert not _valid_assessment({**base, "question": None, "target_domain": "business", "target_key": "existing_customers"})


def test_valid_assessment_allows_a_pure_sufficiency_verdict_with_no_question():
    assert _valid_assessment({
        "answer_ready": True, "confidence": 85, "missing_information": [],
        "next_question_required": False, "question": None, "target_domain": None, "target_key": None,
    })


def test_valid_assessment_rejects_a_confidence_score_outside_0_to_100():
    assert not _valid_assessment({
        "answer_ready": True, "confidence": 150, "missing_information": [], "next_question_required": False,
    })


def test_build_priority_context_excludes_unrelated_older_facts_outright():
    """Concrete fix for "previous: relationship fights, current: what about
    my career" — usable_facts() is expected to have ALREADY filtered `facts`
    to the active category before this is called; this only asserts the
    assembly itself never re-introduces anything outside that filter."""
    focus = {"topic": "career", "active_decision": None, "known_for_decision": {}, "missing_for_decision": []}
    facts = {"career": {"occupation": {"value": "developer"}}}  # already filtered — no relationships domain
    text = build_priority_context("What about my career?", focus, facts)
    assert "developer" in text
    assert "relationship" not in text.lower()
    assert "fight" not in text.lower()


def test_build_priority_context_puts_the_current_message_first():
    text = build_priority_context("Will clothing business work for me?", {}, {})
    assert text.startswith("Current message: Will clothing business work for me?")


def test_values_present_checks_substance_not_exact_wording():
    assert _values_present("Clothing lines up well with your chart, given your strongest planet Venus.", ["clothing", "Venus"])
    assert not _values_present("Clothing looks fine.", ["Venus"])


async def test_compose_final_reply_returns_the_deterministic_fallback_when_disabled():
    fallback = "You're thinking clothing, funded by savings."
    assert await compose_final_reply("msg", {}, "ctx", {}, ["clothing"], fallback, "en") == fallback


async def test_compose_final_reply_skips_the_provider_entirely_when_no_api_key(monkeypatch):
    import openai
    from app.core.config import Settings

    monkeypatch.setattr(
        "app.services.chat_gpt_mediator.get_settings",
        lambda: Settings(chat_interpretation_layer_enabled=True, openai_api_key=""),
    )
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: pytest.fail("provider must not run"))
    fallback = "You're thinking clothing, funded by savings."
    assert await compose_final_reply("msg", {}, "ctx", {}, ["clothing"], fallback, "en") == fallback


def test_known_categories_never_includes_none_as_a_real_choice():
    """"none" is the explicit escape hatch in the prompt (see
    _INTENT_RESCUE_SYSTEM_PROMPT) — it must never be a category the rest of
    the pipeline could mistake for a real, engine-recognized one."""
    assert "none" not in _KNOWN_CATEGORIES


async def test_normalize_input_skips_the_provider_entirely_when_engine_only(monkeypatch):
    import openai
    from app.core.config import Settings

    monkeypatch.setattr(
        "app.services.chat_gpt_mediator.get_settings",
        lambda: Settings(chat_gpt_mediator_enabled=True, openai_api_key="test"),
    )
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: pytest.fail("provider must not run"))
    assert await normalize_input("elation ship", "en", engine_only=True) == "elation ship"


def test_polarity_signature_distinguishes_negated_from_stated():
    """This is the deterministic check normalize_input's own fail-closed
    fallback relies on — a cleanup that changes this signature is rejected
    regardless of how plausible it looks, without ever needing to inspect
    what a provider actually returned."""
    assert _polarity_signature("I am married") != _polarity_signature("I am not married")
    assert _polarity_signature("I am married") == _polarity_signature("main married hoon")


def test_fact_tokens_extracts_dates_numbers_and_names():
    """This is the deterministic check beautify_reply's fail-closed fallback
    relies on — a rewrite missing any of these tokens is rejected."""
    tokens = _fact_tokens("The window is 2025-10-31 to 2028-09-06. You mentioned Priya and 6 months.")
    assert "2025-10-31" in tokens
    assert "2028-09-06" in tokens
    assert "6" in tokens
    assert "Priya" in tokens


def test_build_facts_to_preserve_excludes_a_dates_own_internal_digit_fragments():
    """Caught live: compose_final_reply's caller used to pass raw
    _fact_tokens(text) as facts_to_preserve, which included "03"/"18" as
    their OWN standalone required facts (since _NUMBER_RE also matches
    digits INSIDE an already-captured date) — rejecting a correct reply
    that reformatted "2027-03-18" to "March 2027" as if it had dropped a
    fact. The full date is preserved as a single unit instead."""
    facts = build_facts_to_preserve("The window is 2027-03-18 to 2029-10-05, led by Mercury.")
    assert "2027-03-18" in facts
    assert "2029-10-05" in facts
    assert "Mercury" in facts
    assert "03" not in facts
    assert "18" not in facts


def test_build_facts_to_preserve_keeps_a_genuinely_standalone_number():
    facts = build_facts_to_preserve("You mentioned 6 months of savings.")
    assert "6" in facts


def test_date_expressed_accepts_a_natural_language_reformatting_of_the_same_date():
    """compose_final_reply's own system prompt explicitly invites this
    reformatting for readability — it must never be treated as dropping the
    fact, only a genuinely DIFFERENT date should fail."""
    assert _date_expressed("2027-03-18", "from March 18, 2027 onward")
    assert _date_expressed("2027-03-18", "2027-03-18")
    assert not _date_expressed("2027-03-18", "from March 2028 onward")
    assert not _date_expressed("2027-03-18", "no date mentioned at all")


def test_interpretation_facts_preserved_uses_date_expressed_for_date_shaped_facts():
    reply = "The stronger window runs from March 18, 2027 to October 5, 2029, led by Mercury."
    assert _interpretation_facts_preserved(reply, ["2027-03-18", "2029-10-05", "Mercury"])
    assert not _interpretation_facts_preserved(reply, ["2027-03-18", "Priya"])


def test_interpretation_has_no_fabricated_facts_allows_a_signal_only_present_in_source_data():
    """Caught live: the deterministic fallback text only ever mentioned the
    FUTURE window's period lord (Mercury) — but the real structured engine
    result also names the CURRENT period's lord (Venus/Jupiter), and GPT
    correctly used that richer, genuinely real signal. This must count as a
    strictly better answer, not fabrication, as long as it's traceable to
    the source data GPT was actually given."""
    fallback = "The strongest window for financial growth is 2027-03-18 to 2029-10-05, under a period led by Mercury."
    reply = "You're currently in a period led by Venus and Jupiter. The strongest window is March 2027 to October 2029, led by Mercury."
    source_text = '{"current_period": {"mahadasha_lord": "Venus", "antardasha_lord": "Jupiter"}}'
    assert _interpretation_has_no_fabricated_facts(reply, fallback, ["2027-03-18", "2029-10-05", "Mercury"], source_text)
    # A planet with NO basis anywhere (fallback, facts_to_preserve, or
    # source data) is still correctly rejected as fabrication.
    invented = "You're currently in a period led by Saturn and Rahu, unrelated to anything given."
    assert not _interpretation_has_no_fabricated_facts(invented, fallback, ["2027-03-18", "2029-10-05", "Mercury"], source_text)
