"""Coverage for app.services.chat_gpt_mediator — deliberately does NOT mock
or simulate any OpenAI/GPT response (per explicit instruction: no GPT usage
in tests, mocked or otherwise). What's tested instead is everything that's
real, deterministic logic with no provider involved at all: the
polarity/fact-token safety checks these functions gate on, and that each
function correctly never constructs a provider client when disabled or
running engine_only. The actual provider round-trip is exercised only by
live, manual verification (see the plan file), never by the automated suite."""
import pytest

from app.services.chat_gpt_mediator import _fact_tokens, _polarity_signature, normalize_input


async def test_normalize_input_returns_message_unchanged_when_disabled():
    assert await normalize_input("elation ship", "en") == "elation ship"


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
