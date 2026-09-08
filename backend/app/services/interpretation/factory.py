from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.interpretation.base import Interpreter
from app.services.interpretation.claude_interpreter import ClaudeInterpreter
from app.services.interpretation.templates import TemplateInterpreter


def _should_use_ai(settings: Settings) -> bool:
    """Both an explicit opt-in AND a key are required — an API key present
    on its own does nothing. Astrology's numbers are calculated (Swiss
    Ephemeris + classical rules), never AI-guessed; this only decides
    whether prose *explaining* those numbers may come from an LLM instead
    of the deterministic template interpreter."""
    return settings.use_ai_interpretation and bool(settings.anthropic_api_key)


@lru_cache
def get_interpreter() -> Interpreter:
    settings = get_settings()
    if _should_use_ai(settings):
        return ClaudeInterpreter()
    return TemplateInterpreter()
