"""Text-to-speech provider interface + stub implementation.

To wire up a real provider: implement a new class satisfying `TtsProvider`
(e.g. GoogleTtsProvider using google-cloud-texttospeech) and add it to
`get_tts_provider()` below, keyed off `settings.tts_provider`. It should
upload the synthesized audio somewhere (e.g. S3/GCS) and return a URL —
this interface deliberately returns a URL, not raw bytes, so the API layer
never has to change shape once a real provider lands.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from app.core.config import get_settings

Language = Literal["en", "hi"]


@dataclass(frozen=True)
class SynthesisResult:
    audio_url: str | None
    stub: bool
    note: str


class TtsProvider(ABC):
    name: str

    @abstractmethod
    async def synthesize(self, text: str, language: Language) -> SynthesisResult: ...


class StubTtsProvider(TtsProvider):
    name = "stub"

    async def synthesize(self, text: str, language: Language) -> SynthesisResult:
        return SynthesisResult(
            audio_url=None,
            stub=True,
            note=(
                "No real TTS provider is configured. The frontend should fall back to "
                "on-device TTS with this text. Configure a real provider (Google/Azure/AWS) "
                "and set TTS_PROVIDER to get a real audio_url here."
            ),
        )


def get_tts_provider() -> TtsProvider:
    settings = get_settings()
    if settings.tts_provider == "stub":
        return StubTtsProvider()
    raise NotImplementedError(f"TTS provider '{settings.tts_provider}' is not implemented yet")
