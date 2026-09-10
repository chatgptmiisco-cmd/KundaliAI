"""End-to-end coverage for POST /chat/astro — the free-text "ask a question,
get a real-chart-grounded answer" endpoint. Runs against the template (non-
LLM) interpreter since no ANTHROPIC_API_KEY is set in the test environment,
so this locks in the deterministic keyword-routed chat_reply wired through
the real endpoint (context building, history persistence), not just the
interpreter unit in isolation (see test_interpretation_templates.py).

/chat/astro is gated behind the 'strategy' tier; the test environment runs
with ALL_FEATURES_FREE forced off (see conftest.py) so tier-gating tests
elsewhere stay meaningful, which means these tests bypass it explicitly the
same way test_feature_gating.py does."""
import pytest

from app.core.config import Settings
from tests.test_api_e2e import _signup_and_set_birth_data


def _unlock_strategy_tier(monkeypatch):
    monkeypatch.setattr("app.api.deps.get_settings", lambda: Settings(all_features_free=True))


async def test_chat_astro_answers_a_real_question_and_persists_history(client, monkeypatch):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": "How's my career looking?", "language": "en"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "en"
    assert body["reply"]
    # Real, chart-grounded text — not the old "please clarify" stub.
    assert "clarify" not in body["reply"].lower()

    # A second message in the same conversation should see the first as
    # history without erroring (history round-trip through the DB).
    resp2 = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": "What about money?", "language": "en"}
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["reply"]


async def test_chat_astro_answers_in_hindi_when_requested(client, monkeypatch):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": "मेरा करियर कैसा रहेगा?", "language": "hi"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "hi"
    assert body["reply"]


async def test_chat_astro_specializes_by_rishi_id_and_scopes_history_per_rishi(client, monkeypatch):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    # Bhrigu (career & resources) redirects a relationship question to Gargi
    # instead of answering it himself.
    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "Tell me about my marriage prospects", "rishi_id": "bhrigu", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert "Gargi" in resp.json()["reply"]

    # The same question asked of Gargi (relationships) gets a real answer,
    # not a redirect.
    resp2 = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "Tell me about my marriage prospects", "rishi_id": "gargi", "language": "en"},
    )
    assert resp2.status_code == 200, resp2.text
    assert "Gargi" not in resp2.json()["reply"]
    assert "Bhrigu" not in resp2.json()["reply"]


async def test_chat_astro_answers_when_will_i_get_married_from_the_real_prediction_engine(client, monkeypatch):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "When will I get married?", "rishi_id": "gargi", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    # Either a real window (with a date range) or the honest "no window
    # found" line — never the old generic dasha-lord sentence or a refusal.
    assert "probable favorable window" in reply or "I didn't find a strongly favorable window" in reply


async def test_chat_astro_marriage_timing_question_redirects_to_gargi_from_another_rishi(client, monkeypatch):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "When will I get married?", "rishi_id": "bhrigu", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert "Gargi" in resp.json()["reply"]


async def test_chat_astro_answers_hows_my_year_from_the_real_prediction_engine(client, monkeypatch):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "How's my year looking?", "rishi_id": "parashara", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert "overall rating is" in reply and "/10" in reply


@pytest.mark.parametrize(
    "message,rishi_id",
    [
        ("When will I get a promotion?", "bhrigu"),
        ("When will my financial situation improve?", "bhrigu"),
        ("When will I have children?", "gargi"),
        ("When will I settle abroad?", "vasishtha"),
        # Colloquial "will I" phrasing (no explicit "when") is just as common
        # a real-world question and must reach the same engine, not the
        # static topic fallback — caught live before this was added.
        ("Will I settle abroad?", "vasishtha"),
        ("Will I get married?", "gargi"),
    ],
)
async def test_chat_astro_answers_life_event_timing_questions_from_the_real_engine(client, monkeypatch, message, rishi_id):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": message, "rishi_id": rishi_id, "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert "probable favorable window" in reply or "I didn't find a strongly favorable window" in reply


async def test_chat_astro_career_timing_question_redirects_to_bhrigu_from_another_rishi(client, monkeypatch):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "When will I get a promotion?", "rishi_id": "vasishtha", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert "Bhrigu" in resp.json()["reply"]


async def test_chat_astro_plain_career_question_is_not_hijacked_by_career_timing(client, monkeypatch):
    """Regression guard: a non-timing career question (no 'when'/'kab') must
    still get the existing static house-text answer, not the life-event
    engine's window text — same collision class the marriage/year-ahead
    rollout already caught once."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "What career suits me?", "rishi_id": "bhrigu", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert "probable favorable window" not in reply
    assert "I didn't find a strongly favorable window" not in reply


async def test_chat_astro_requires_birth_profile(client):
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "nochat@example.com", "password": "supersecret1", "name": "No Birth", "preferred_language": "en"},
    )
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    resp = await client.post("/api/v1/chat/astro", headers=headers, json={"message": "Hello", "language": "en"})
    assert resp.status_code == 400
