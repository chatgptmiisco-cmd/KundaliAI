from functools import lru_cache, wraps
from contextvars import ContextVar

from app.core.config import Settings, get_settings
from app.services.interpretation.base import Interpreter
from app.services.interpretation.claude_interpreter import ClaudeInterpreter
from app.services.interpretation.openai_interpreter import OpenAIInterpreter
from app.services.interpretation.templates import TemplateInterpreter

_native_execution = ContextVar("native_interpretation", default=False)


def native_chat(function):
    """Request-local policy also covers nested chart/prediction service calls.

    ContextVar avoids changing global settings for concurrent report requests.
    Optional chat styling is separate and cannot author interpretation.
    """
    @wraps(function)
    async def wrapped(*args, **kwargs):
        token = _native_execution.set(True)
        try:
            return await function(*args, **kwargs)
        finally:
            _native_execution.reset(token)
    return wrapped


def _should_use_ai(settings: Settings) -> bool:
    """An explicit opt-in AND at least one provider's key are both required —
    a key present on its own does nothing. Astrology's numbers are calculated
    (Swiss Ephemeris + classical rules), never AI-guessed; this only decides
    whether prose *explaining* those numbers may come from an LLM instead
    of the deterministic template interpreter."""
    return settings.use_ai_interpretation and bool(settings.openai_api_key or settings.anthropic_api_key)


@lru_cache
def _configured_interpreter() -> Interpreter:
    settings = get_settings()
    if not _should_use_ai(settings):
        return TemplateInterpreter()
    # OpenAI is preferred when both keys happen to be set — it's the
    # actively-maintained path (chat's understand-then-explain pipeline in
    # app.services.chat_understanding only has real category detection with
    # OpenAI configured; Claude's chat_reply still works, just without that).
    if settings.openai_api_key:
        return OpenAIInterpreter()
    return ClaudeInterpreter()


def get_interpreter() -> Interpreter:
    if _native_execution.get():
        return TemplateInterpreter()
    return _configured_interpreter()
