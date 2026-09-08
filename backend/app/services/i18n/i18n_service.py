"""Static server-side string localization (error messages, notifications).

Dynamic content (horoscope text, interpretations) is NOT handled here — that
goes through app.services.interpretation, which asks the LLM directly for
the target language rather than translating a fixed template.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

_DIR = Path(__file__).parent

Lang = Literal["en", "hi"]


@lru_cache
def _load(lang: Lang) -> dict[str, str]:
    path = _DIR / f"strings_{lang}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def t(key: str, lang: Lang = "en") -> str:
    strings = _load(lang if lang in ("en", "hi") else "en")
    return strings.get(key, key)
