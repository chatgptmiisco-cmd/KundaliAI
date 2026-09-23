"""Full end-to-end HTTP contracts for the native-engine chat pipeline —
conversation_engine + native_understanding + user_context_engine +
native_response + chat_beautifier all wired together through the real
/chat/astro endpoint, exercised with `engine_only: True` so a GPT call
anywhere in the request would fail the test outright (see the
`openai.AsyncOpenAI` monkeypatches below).

These two scenarios don't belong to any single module's own test file —
each is a genuine multi-module integration contract — so they get their
own file rather than being folded into one of the per-module suites split
out of the original test_native_intelligence.py."""
import pytest
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models.conversation_state import ConversationState
from app.db.models.user import User
from app.services import life_context_service
from tests.test_api_e2e import _signup_and_set_birth_data


async def test_complete_engine_only_conversation_persists_before_questions(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "all_features_free", True)
    monkeypatch.setattr(get_settings(), "use_ai_interpretation", True)
    monkeypatch.setattr(get_settings(), "openai_api_key", "fake-key-must-not-be-used")
    import openai
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: pytest.fail("engine-only conversation called GPT"))
    headers = await _signup_and_set_birth_data(client)

    async def chat(message, rishi="vyasa"):
        response = await client.post("/api/v1/chat/astro", headers=headers,
                                     json={"message": message, "rishi_id": rishi, "engine_only": True})
        assert response.status_code == 200, response.text
        assert response.json()["response_source"] == "native"
        return response.json()["reply"]

    await chat("I work as a developer.")
    await chat("I want to start an ecommerce business.")
    await chat("I already have paying customers.")
    reply = await chat("Should I leave my job?")
    assert "developer" in reply and "ecommerce" in reply
    assert "savings" in reply.lower()
    async with AsyncSessionLocal() as db:
        state = await db.scalar(select(ConversationState))
        assert state.data["pending"]
    reply = await chat("1. Growth 2. I have six months of savings")
    assert "transition" in reply.lower() or "income plan" in reply.lower()
    await chat("Actually I am a teacher.", "gargi")
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User))
        facts = await life_context_service.get_active_context(db, user.id, ["career"])
        assert facts["career"]["occupation"]["value"] == "teacher"
        history = await life_context_service.get_fact_history(db, user.id, "career", "occupation")
        assert any(f["value"] == "developer" and f["status"] == "superseded" for f in history)


async def test_married_timing_asks_contextual_clarification(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "all_features_free", True)
    headers = await _signup_and_set_birth_data(client)
    response = await client.post("/api/v1/chat/astro", headers=headers,
        json={"message": "I am already married. When will I get married?", "engine_only": True})
    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "already married" in reply
    # Stage 3 — a personalized numbered menu of genuinely different angles,
    # not the old fixed "married life, relationship growth, or another
    # milestone" question.
    assert "1." in reply and "2." in reply
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User))
        facts = await life_context_service.get_active_context(db, user.id, ["relationships"])
        assert facts["relationships"]["relationship_status"]["value"] == "married"
