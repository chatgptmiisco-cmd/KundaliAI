from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.interpretation.base import Interpreter
from app.services.interpretation.claude_interpreter import ClaudeInterpreter
from app.services.interpretation.openai_interpreter import OpenAIInterpreter
from app.services.interpretation.templates import TemplateInterpreter


def _should_use_ai(settings: Settings) -> bool:
    """An explicit opt-in AND at least one provider's key are both required —
    a key present on its own does nothing. Astrology's numbers are calculated
    (Swiss Ephemeris + classical rules), never AI-guessed; this only decides
    whether prose *explaining* those numbers may come from an LLM instead
    of the deterministic template interpreter."""
    return settings.use_ai_interpretation and bool(settings.openai_api_key or settings.anthropic_api_key)


@lru_cache
def get_interpreter() -> Interpreter:
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
