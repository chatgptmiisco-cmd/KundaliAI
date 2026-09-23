"""Coverage for app.services.chat_beautifier — the optional, GPT-adjacent
presentation selector that can only pick from a small set of pre-reviewed
connective-phrase substitutions, never author free text (see the module's
own docstring). Split out of the original combined test_native_intelligence
.py so each new native-engine module has its own dedicated test file.

Hindi/hinglish coverage below is new: REPLACEMENTS used to be English-only
(chat_beautifier.beautify skipped any other language entirely) — it's now
a per-language table, keyed by the same 3 edit IDs regardless of language,
so the GPT system prompt's allowed-IDs list stays language-agnostic while
the actual substituted phrase matches whichever language's native reply
this is being applied to."""
import pytest

from app.services.chat_beautifier import _SYSTEM_PROMPT, apply_style, beautify


def test_system_prompt_says_json_literally():
    """Regression guard for a real bug caught live: OpenAI's Chat
    Completions API rejects response_format={"type": "json_object"} with a
    400 ("'messages' must contain the word 'json' in some form") unless the
    literal word appears somewhere in the messages — the system prompt
    describing the desired {"edits": [...]} shape isn't enough on its own.
    This isn't a quota/outage failure like everything else LLM-related in
    this project; it fires on every single call regardless of credits, so
    it's worth a permanent test rather than relying on a live check."""
    assert "json" in _SYSTEM_PROMPT.lower()


@pytest.mark.parametrize("selection", [
    {"answer": "You will marry in 2030"}, {"edits": ["invent_dates"]}, {"edits": [1]}, [],
    {"edits": ["shared"], "prediction": "guaranteed"},
])
def test_styling_rejects_untrusted_content(selection):
    original = "From what you've shared, Saturn suggests a conditional window in 2028, not a guarantee."
    assert apply_style(original, selection) == original


def test_styling_only_changes_reviewed_connective():
    answer = "From what you've shared, 2028-01-01 to 2029-02-03 is possible, not certain."
    assert apply_style(answer, {"edits": ["shared"]}) == answer.replace("From what you've shared, ", "Based on what you've told me, ")


def test_styling_supports_hindi_with_its_own_reviewed_phrasing():
    answer = "आपने जो बताया है, उसके अनुसार — यह अवधि अनुकूल है।"
    styled = apply_style(answer, {"edits": ["shared"]}, "hi")
    assert styled == answer.replace("आपने जो बताया है, उसके अनुसार — ", "आपने जो साझा किया, उसके अनुसार — ")
    # An English-only edit id used against Hindi text that doesn't contain
    # the English phrase is a safe no-op, not an error or a mixed-language mess.
    assert apply_style(answer, {"edits": ["also"]}, "hi") == answer.replace(" वहीं, ", " इसके अलावा, ")


def test_styling_supports_hinglish_with_its_own_shared_phrasing():
    answer = "Aapne jo bataya hai, uske mutabik — yeh period accha hai."
    styled = apply_style(answer, {"edits": ["shared"]}, "hinglish")
    assert styled == answer.replace("Aapne jo bataya hai, uske mutabik — ", "Aapne jo share kiya, uske hisaab se — ")


def test_styling_unrecognized_language_falls_back_to_english_table():
    answer = "From what you've shared, this looks favorable."
    assert apply_style(answer, {"edits": ["shared"]}, "fr") == apply_style(answer, {"edits": ["shared"]}, "en")


async def test_engine_only_never_constructs_provider(monkeypatch):
    import openai
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: pytest.fail("provider must not run"))
    assert await beautify("Native answer", "en", engine_only=True) == "Native answer"


async def test_provider_failure_returns_full_native_answer(monkeypatch):
    from app.core.config import Settings
    import openai
    # chat_gpt_mediator_enabled explicitly False — this test targets the
    # substitution mechanism specifically, and must not silently pick up a
    # developer's local .env override of the OTHER (newer) GPT path, which
    # this same beautify() call now dispatches to first when enabled.
    monkeypatch.setattr("app.services.chat_beautifier.get_settings", lambda: Settings(chat_beautification_enabled=True, chat_gpt_mediator_enabled=False, openai_api_key="test"))
    def fail(**kw):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr(openai, "AsyncOpenAI", fail)
    assert await beautify("Complete native answer", "en") == "Complete native answer"


async def test_beautify_no_longer_skips_hindi_outright(monkeypatch):
    """Regression guard for the old `if language != "en": return answer`
    gate — Hindi/Hinglish must now actually reach the provider call (and
    the language-aware apply_style above), not bail out before ever trying."""
    from app.core.config import Settings
    import openai

    # chat_gpt_mediator_enabled explicitly False — same isolation reasoning
    # as test_provider_failure_returns_full_native_answer above.
    monkeypatch.setattr(
        "app.services.chat_beautifier.get_settings",
        lambda: Settings(chat_beautification_enabled=True, chat_gpt_mediator_enabled=False, openai_api_key="test"),
    )

    class _FakeMessage:
        content = '{"edits": ["shared"]}'

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    class _FakeCompletions:
        async def create(self, **kwargs):
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: _FakeClient())

    answer = "आपने जो बताया है, उसके अनुसार — यह अवधि अनुकूल है।"
    result = await beautify(answer, "hi")
    assert result == answer.replace("आपने जो बताया है, उसके अनुसार — ", "आपने जो साझा किया, उसके अनुसार — ")
