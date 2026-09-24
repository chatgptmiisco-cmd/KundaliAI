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
    _KNOWN_CATEGORIES, _fact_tokens, _polarity_signature, answer_unmapped, classify_unmapped_intent, normalize_input,
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
