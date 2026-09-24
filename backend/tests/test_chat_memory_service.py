"""Coverage for app.services.chat_memory_service — retrieval over a user's
own older chat turns (see that module's docstring for why it exists: the
raw history window in chat.py only sends the most recent ~20 messages to
the LLM, and this covers general conversational context that fell out of
that window and was never captured as a durable structured fact either).

No live OpenAI calls here (the test environment deliberately has none
configured — see conftest.py); embed_text/embed_turn are monkeypatched
where a turn needs an embedding, matching the technique used throughout
this project for every other OpenAI-adjacent test."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.db.base import AsyncSessionLocal
from app.db.models.chat import ChatMessage
from app.services import chat_memory_service
from tests.test_api_e2e import _signup_and_set_birth_data


def test_cosine_similarity_of_identical_vectors_is_one():
    v = [0.5, 0.5, 0.5]
    assert chat_memory_service.cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_of_orthogonal_vectors_is_zero():
    assert chat_memory_service.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_handles_mismatched_or_empty_vectors_without_raising():
    assert chat_memory_service.cosine_similarity([], [1.0]) == 0.0
    assert chat_memory_service.cosine_similarity([1.0, 2.0], [1.0]) == 0.0
    assert chat_memory_service.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


async def test_embed_text_returns_none_on_failure_never_raises(monkeypatch):
    class _BoomClient:
        class embeddings:
            @staticmethod
            async def create(**kwargs):
                raise RuntimeError("network exploded")

    monkeypatch.setattr("app.services.chat_memory_service.get_settings", lambda: type(
        "S", (), {"openai_api_key": "sk-fake", "embedding_model": "text-embedding-3-small"}
    )())

    import openai
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kwargs: _BoomClient())

    result = await chat_memory_service.embed_text("hello")
    assert result is None


async def test_embed_text_returns_none_when_no_api_key_configured(monkeypatch):
    monkeypatch.setattr("app.services.chat_memory_service.get_settings", lambda: type(
        "S", (), {"openai_api_key": None, "embedding_model": "text-embedding-3-small"}
    )())
    assert await chat_memory_service.embed_text("hello") is None


async def test_retrieve_relevant_turns_skips_the_query_when_conversation_is_short(client, monkeypatch):
    """exclude_ids_below=0 (the conversation hasn't filled the raw history
    window yet) must return [] WITHOUT ever calling embed_text — asserted
    by making embed_text raise if it's called at all."""
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    async def _boom(*args, **kwargs):
        raise AssertionError("embed_text should not be called when exclude_ids_below is 0")

    monkeypatch.setattr(chat_memory_service, "embed_text", _boom)

    async with AsyncSessionLocal() as db:
        result = await chat_memory_service.retrieve_relevant_turns(
            db, user_id, "bhrigu", "when will I get promoted?", exclude_ids_below=0,
        )
    assert result == []


async def test_retrieve_relevant_turns_ranks_by_similarity_and_respects_min_similarity(client, monkeypatch):
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    async with AsyncSessionLocal() as db:
        old_time = datetime.now(timezone.utc) - timedelta(days=3)
        close_match = ChatMessage(
            user_id=user_id, role="assistant", content="reply about startup",
            language="en", rishi_id="bhrigu", created_at=old_time,
            embedding=json.dumps([1.0, 0.0, 0.0]),
            embedding_source_text="User: I work at a startup, growth has been slow.\nAssistant: reply about startup",
        )
        weak_match = ChatMessage(
            user_id=user_id, role="assistant", content="reply about something unrelated",
            language="en", rishi_id="bhrigu", created_at=old_time,
            embedding=json.dumps([0.0, 1.0, 0.0]),
            embedding_source_text="User: totally unrelated tangent.\nAssistant: reply about something unrelated",
        )
        db.add_all([close_match, weak_match])
        await db.commit()
        highest_id = max(close_match.id, weak_match.id)

        async def _fake_embed_text(text):
            return [1.0, 0.0, 0.0]  # identical direction to close_match only

        monkeypatch.setattr(chat_memory_service, "embed_text", _fake_embed_text)

        result = await chat_memory_service.retrieve_relevant_turns(
            db, user_id, "bhrigu", "how's my job going", exclude_ids_below=highest_id + 1,
        )

    assert len(result) == 1
    assert "startup" in result[0]["text"]
    assert result[0]["when"]


async def test_retrieve_relevant_turns_is_scoped_to_the_same_rishi(client, monkeypatch):
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    async with AsyncSessionLocal() as db:
        other_rishi_row = ChatMessage(
            user_id=user_id, role="assistant", content="reply from a different rishi's conversation",
            language="en", rishi_id="gargi",
            embedding=json.dumps([1.0, 0.0]),
            embedding_source_text="User: something.\nAssistant: reply from a different rishi's conversation",
        )
        db.add(other_rishi_row)
        await db.commit()
        highest_id = other_rishi_row.id

        async def _fake_embed_text(text):
            return [1.0, 0.0]

        monkeypatch.setattr(chat_memory_service, "embed_text", _fake_embed_text)

        result = await chat_memory_service.retrieve_relevant_turns(
            db, user_id, "bhrigu", "anything", exclude_ids_below=highest_id + 1,
        )
    assert result == []


async def test_retrieve_native_turns_never_surfaces_a_past_question_as_a_fact(client):
    """Regression guard for a real, reproduced bug: a past QUESTION ("What
    does my kundli say about marriage and partner?") was retrieved and
    quoted back exactly like a stated fact, wrapped in "if that situation
    has changed" phrasing that only makes sense for an actual fact."""
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    async with AsyncSessionLocal() as db:
        db.add(ChatMessage(
            user_id=user_id, role="user",
            content="What does my kundli say about marriage and partner?",
            language="en", rishi_id="gargi",
        ))
        db.add(ChatMessage(
            user_id=user_id, role="user", content="I am already thinking about marriage seriously.",
            language="en", rishi_id="gargi",
        ))
        await db.commit()

        result = await chat_memory_service.retrieve_native_turns(db, user_id, ["marriage"], "marriage")
    assert all("?" not in item["text"] for item in result)
    assert any("thinking about marriage" in item["text"] for item in result)


async def test_retrieve_native_turns_does_not_cross_pollinate_via_the_shared_goals_domain(client):
    """Regression guard for a real, reproduced bug: a bare "money" question
    resurfaced "there is no growth in my job" (a career statement) as "an
    earlier related conversation you said" — purely because _CATEGORY_
    DOMAINS["career"] and _CATEGORY_DOMAINS["money"] both include "goals",
    a deliberately broad catch-all meant for fact retrieval elsewhere, not a
    genuine relevance signal for this narrative callback."""
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    async with AsyncSessionLocal() as db:
        db.add(ChatMessage(
            user_id=user_id, role="user", content="there is no growth in my job",
            language="en", rishi_id="bhrigu",
        ))
        await db.commit()

        result = await chat_memory_service.retrieve_native_turns(db, user_id, ["money"], "money")
    assert result == []


async def test_retrieve_native_turns_excludes_already_surfaced_quotes(client):
    """Regression guard: the same past statement resurfaced as a callback
    on every subsequent turn the topic recurred, since nothing tracked what
    had already been shown once (see chat.py's surfaced_quote_ids)."""
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    async with AsyncSessionLocal() as db:
        row = ChatMessage(
            user_id=user_id, role="user", content="I am already thinking about marriage seriously.",
            language="en", rishi_id="gargi",
        )
        db.add(row)
        await db.commit()

        first = await chat_memory_service.retrieve_native_turns(db, user_id, ["marriage"], "marriage")
        assert len(first) == 1

        second = await chat_memory_service.retrieve_native_turns(
            db, user_id, ["marriage"], "marriage", exclude_ids={row.id},
        )
    assert second == []
