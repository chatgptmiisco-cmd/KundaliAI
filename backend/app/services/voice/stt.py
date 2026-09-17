"""Speech-to-text provider interface + implementations.

The frontend can always send pre-transcribed text directly to /chat/astro,
so STT is an enhancement, not a hard dependency — the stub here returns an
honest "not configured" response rather than pretending to transcribe.

To wire up another provider: implement a new class satisfying `SttProvider`
(e.g. GoogleSttProvider using google-cloud-speech) and add it to
`get_stt_provider()` below, keyed off `settings.stt_provider`.
"""
from abc import ABC, abstractmethod
from typing import Literal

from app.core.config import get_settings

Language = Literal["en", "hi", "hinglish"]

# Whisper-family models have no "hinglish" language code — there isn't one —
# so for genuinely code-switched Hindi-English speech we deliberately don't
# pass a language hint at all (omitted lets the model auto-detect per
# segment) and lean on `prompt` instead to bias it toward Roman-script,
# code-switched output. This is best-effort, not a guarantee: the model can
# still render a Hindi-heavy stretch in Devanagari.
_STT_LANGUAGE: dict[Language, str | None] = {"en": "en", "hi": "hi", "hinglish": None}
_STT_PROMPT: dict[Language, str | None] = {
    "en": None,
    "hi": None,
    "hinglish": (
        "This is casual Hinglish speech — mixed Hindi and English, spoken the way "
        "urban Indian friends talk. Transcribe it in Roman/Latin script throughout, "
        'never Devanagari, spelling Hindi words phonetically (e.g. "kya", "shaadi", '
        '"paisa").'
    ),
}


class SttProvider(ABC):
    name: str

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: Language, filename: str) -> str: ...


class StubSttProvider(SttProvider):
    name = "stub"

    async def transcribe(self, audio_bytes: bytes, language: Language, filename: str) -> str:
        raise NotImplementedError(
            "No real STT provider is configured (settings.stt_provider='stub'). "
            "Send pre-transcribed text to /chat/astro instead, or configure a "
            "real provider (OpenAI/Google/Azure/AWS) and set STT_PROVIDER."
        )


class OpenAISttProvider(SttProvider):
    """Whisper-family speech-to-text via OpenAI — reuses the same API key
    already configured for chat (Settings.openai_api_key), no separate
    provider account needed. whisper-1 is the default (see Settings.stt_model)
    since it's available on every project without extra enablement; the
    newer gpt-4o-*-transcribe models are opt-in via STT_MODEL."""

    name = "openai"

    def __init__(self) -> None:
        from openai import AsyncOpenAI  # local import: only needed on this path

        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.stt_model

    async def transcribe(self, audio_bytes: bytes, language: Language, filename: str) -> str:
        kwargs: dict[str, str] = {}
        whisper_language = _STT_LANGUAGE[language]
        if whisper_language:
            kwargs["language"] = whisper_language
        prompt = _STT_PROMPT[language]
        if prompt:
            kwargs["prompt"] = prompt
        response = await self._client.audio.transcriptions.create(
            model=self._model, file=(filename, audio_bytes), **kwargs,
        )
        return response.text.strip()


def get_stt_provider() -> SttProvider:
    settings = get_settings()
    if settings.stt_provider == "stub":
        return StubSttProvider()
    if settings.stt_provider == "openai":
        return OpenAISttProvider()
    raise NotImplementedError(f"STT provider '{settings.stt_provider}' is not implemented yet")
