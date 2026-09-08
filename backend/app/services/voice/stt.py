"""Speech-to-text provider interface + stub implementation.

The frontend can always send pre-transcribed text directly to /chat/astro,
so STT is an enhancement, not a hard dependency — the stub here returns an
honest "not configured" response rather than pretending to transcribe.

To wire up a real provider: implement a new class satisfying `SttProvider`
(e.g. GoogleSttProvider using google-cloud-speech) and add it to
`get_stt_provider()` below, keyed off `settings.stt_provider`.
"""
from abc import ABC, abstractmethod
from typing import Literal

from app.core.config import get_settings

Language = Literal["en", "hi"]


class SttProvider(ABC):
    name: str

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: Language) -> str: ...


class StubSttProvider(SttProvider):
    name = "stub"

    async def transcribe(self, audio_bytes: bytes, language: Language) -> str:
        raise NotImplementedError(
            "No real STT provider is configured (settings.stt_provider='stub'). "
            "Send pre-transcribed text to /chat/astro instead, or configure a "
            "real provider (Google/Azure/AWS) and set STT_PROVIDER."
        )


def get_stt_provider() -> SttProvider:
    settings = get_settings()
    if settings.stt_provider == "stub":
        return StubSttProvider()
    raise NotImplementedError(f"STT provider '{settings.stt_provider}' is not implemented yet")
