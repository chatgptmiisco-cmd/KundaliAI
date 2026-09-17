import pytest

from app.core.config import Settings
from app.services.voice.stt import OpenAISttProvider, StubSttProvider, get_stt_provider


def test_get_stt_provider_defaults_to_stub(monkeypatch):
    monkeypatch.setattr("app.services.voice.stt.get_settings", lambda: Settings(stt_provider="stub"))
    assert isinstance(get_stt_provider(), StubSttProvider)


async def test_stub_provider_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        await StubSttProvider().transcribe(b"", "en", "audio.m4a")


def test_get_stt_provider_returns_openai_when_configured(monkeypatch):
    monkeypatch.setattr(
        "app.services.voice.stt.get_settings",
        lambda: Settings(stt_provider="openai", openai_api_key="sk-test", stt_model="whisper-1"),
    )
    provider = get_stt_provider()
    assert isinstance(provider, OpenAISttProvider)
    assert provider.name == "openai"


def test_get_stt_provider_raises_for_unimplemented_provider(monkeypatch):
    monkeypatch.setattr("app.services.voice.stt.get_settings", lambda: Settings(stt_provider="google"))
    with pytest.raises(NotImplementedError):
        get_stt_provider()
