"""Coverage for Phase 2's historical-validation / prediction-feedback loop
(product spec §15/§30): a real, falsifiable past-event question the app
asked (see app.api.v1.chat's vague-past-event fallback) gets tracked in
`PredictionFeedback`, and a confirmed/partial answer becomes a real
`LifeEvent` — see app.services.prediction_feedback_service and chat.py's
pending_prediction_feedback wiring.
"""
from datetime import datetime, timedelta, timezone

from app.api.v1 import chat as chat_module
from app.core.config import Settings
from app.db.base import AsyncSessionLocal
from app.services import life_context_service, prediction_feedback_service, user_service
from app.services.chat_understanding import ChatUnderstanding, PredictionFeedbackReport
from tests.test_api_e2e import _signup_and_set_birth_data


def _unlock_strategy_tier(monkeypatch):
    monkeypatch.setattr("app.api.deps.get_settings", lambda: Settings(all_features_free=True))


async def _real_user_id(client) -> str:
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    return headers, profile.json()["id"]


_WINDOW_START = datetime(2016, 1, 1, tzinfo=timezone.utc)
_WINDOW_END = datetime(2016, 6, 1, tzinfo=timezone.utc)


async def test_create_pending_feedback_dedups_the_same_window(client):
    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        first = await prediction_feedback_service.create_pending_feedback(
            db, user_id, "career", _WINDOW_START, _WINDOW_END, "did you change roles then?"
        )
        second = await prediction_feedback_service.create_pending_feedback(
            db, user_id, "career", _WINDOW_START, _WINDOW_END, "did you change roles then?"
        )
        assert first.id == second.id  # no duplicate unanswered row for the identical window


async def test_get_pending_feedback_returns_the_most_recent_unanswered(client):
    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        older = await prediction_feedback_service.create_pending_feedback(
            db, user_id, "career", _WINDOW_START, _WINDOW_END, "q1"
        )
        newer_start = _WINDOW_START + timedelta(days=1000)
        newer = await prediction_feedback_service.create_pending_feedback(
            db, user_id, "relationships", newer_start, newer_start + timedelta(days=90), "q2"
        )
        pending = await prediction_feedback_service.get_pending_feedback(db, user_id)
        assert pending.id == newer.id
        assert pending.id != older.id


async def test_record_feedback_rejects_an_invalid_verdict(client):
    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        row = await prediction_feedback_service.create_pending_feedback(
            db, user_id, "career", _WINDOW_START, _WINDOW_END, "q"
        )
        result = await prediction_feedback_service.record_feedback(db, user_id, row.id, "definitely", "x")
        assert result is None
        # Still pending — the bad write never happened.
        assert await prediction_feedback_service.get_pending_feedback(db, user_id) is not None


async def test_record_feedback_sets_fields_and_removes_it_from_pending(client):
    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        row = await prediction_feedback_service.create_pending_feedback(
            db, user_id, "career", _WINDOW_START, _WINDOW_END, "q"
        )
        result = await prediction_feedback_service.record_feedback(
            db, user_id, row.id, "correct", "I changed jobs to product management"
        )
        assert result.feedback == "correct"
        assert result.confirmed_detail == "I changed jobs to product management"
        assert result.answered_at is not None
        assert await prediction_feedback_service.get_pending_feedback(db, user_id) is None


async def test_chat_resolves_pending_feedback_and_creates_a_life_event(client, monkeypatch):
    """A crafted ChatUnderstanding.prediction_feedback (classify_message
    itself needs a real OpenAI call the test environment deliberately
    disables — see conftest.py) stands in for what the LLM would produce
    when a user confirms a past-event candidate. What's under test is
    chat.py's OWN wiring: does it record the feedback AND create a real
    LifeEvent anchored to the window's own start year."""
    _unlock_strategy_tier(monkeypatch)
    headers, user_id = await _real_user_id(client)

    async with AsyncSessionLocal() as db:
        pending = await prediction_feedback_service.create_pending_feedback(
            db, user_id, "career", _WINDOW_START, _WINDOW_END, "did you change roles around 2016?"
        )

    async def _fake_classify_message(*args, **kwargs):
        return ChatUnderstanding(
            categories=[],
            prediction_feedback=PredictionFeedbackReport(
                verdict="correct", detail="I moved from engineering into product management"
            ),
        )

    monkeypatch.setattr(chat_module, "classify_message", _fake_classify_message)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "Yes, I moved from engineering into product management then", "language": "en"},
    )
    assert resp.status_code == 200, resp.text

    async with AsyncSessionLocal() as db:
        resolved = await prediction_feedback_service.get_pending_feedback(db, user_id)
        assert resolved is None  # no longer pending

        timeline = await life_context_service.get_timeline(db, user_id)
        assert any(
            e["description"] == "I moved from engineering into product management" and e["year"] == 2016
            for e in timeline
        )


async def test_chat_surfaces_the_resolution_verdict_into_context_for_the_reply(client, monkeypatch):
    """Phase 10 — the reply-generating context must see WHICH verdict a
    pending prediction-feedback question was just resolved with (so it can
    acknowledge an "incorrect" one honestly instead of ignoring or
    defending it — see openai_interpreter.py's resolved_prediction_feedback
    prompt paragraph). Captures the real context dict chat.py builds by
    monkeypatching TemplateInterpreter.chat_reply, same technique used
    throughout this project for context-inspection tests."""
    _unlock_strategy_tier(monkeypatch)
    headers, user_id = await _real_user_id(client)

    async with AsyncSessionLocal() as db:
        await prediction_feedback_service.create_pending_feedback(
            db, user_id, "career", _WINDOW_START, _WINDOW_END, "did you change roles around 2016?"
        )

    async def _fake_classify_message(*args, **kwargs):
        return ChatUnderstanding(
            categories=[], prediction_feedback=PredictionFeedbackReport(verdict="incorrect", detail=None),
        )

    monkeypatch.setattr(chat_module, "classify_message", _fake_classify_message)

    captured = {}

    async def _fake_chat_reply(history, context, language):
        captured.update(context)
        return "ok"

    from app.services.interpretation.templates import TemplateInterpreter
    monkeypatch.setattr("app.services.native_response.compose", _fake_chat_reply)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "No, that never happened", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert captured.get("resolved_prediction_feedback") == {
        "verdict": "incorrect", "domain": "career", "question_asked": "did you change roles around 2016?",
    }
