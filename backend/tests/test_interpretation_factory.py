"""Locks in the calculation-first guarantee: an ANTHROPIC_API_KEY alone must
never be enough to switch narrative generation over to a live LLM call —
USE_AI_INTERPRETATION has to be explicitly true as well. Astrology's numbers
come from Swiss Ephemeris + classical rules regardless of this setting; this
only gates whether the *prose* may come from Claude instead of the
deterministic template interpreter.
"""
from app.core.config import Settings
from app.services.interpretation.factory import _should_use_ai


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


def test_api_key_alone_does_not_enable_ai():
    settings = _settings(anthropic_api_key="sk-test-key", use_ai_interpretation=False)
    assert _should_use_ai(settings) is False


def test_flag_alone_without_a_key_does_not_enable_ai():
    settings = _settings(anthropic_api_key=None, use_ai_interpretation=True)
    assert _should_use_ai(settings) is False


def test_no_key_and_flag_off_does_not_enable_ai():
    settings = _settings(anthropic_api_key=None, use_ai_interpretation=False)
    assert _should_use_ai(settings) is False


def test_both_flag_and_key_present_enables_ai():
    settings = _settings(anthropic_api_key="sk-test-key", use_ai_interpretation=True)
    assert _should_use_ai(settings) is True


def test_use_ai_interpretation_defaults_to_false():
    settings = Settings()
    assert settings.use_ai_interpretation is False
