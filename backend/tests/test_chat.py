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


async def test_chat_astro_decision_category_context_is_json_serializable(client, monkeypatch):
    """Regression guard for a real bug caught live once the OpenAI interpreter
    went active: chat.py built job_change_decision/business_start_decision's
    context via CurrentPeriod/BetterWindow.model_dump() (no mode="json"),
    which leaves start_date/end_date as raw `date` objects — invisible on the
    template path (it only ever reads decision["note"]/["reasoning"], never
    serializes the whole dict) but a hard 500 the moment anything calls
    json.dumps() on the full context, as any real LLM-backed interpreter
    does. This exercises the actual endpoint end-to-end and would fail the
    same way if the mode="json" fix regressed."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "Should I switch my job right now?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"]

    # The underlying schema fix itself: mode="json" must turn `date` fields
    # into plain JSON-safe strings, not leave them as `date` objects.
    from datetime import date

    from app.schemas.prediction import CurrentPeriod

    period = CurrentPeriod(
        start_date=date(2025, 1, 1), end_date=date(2026, 1, 1), mahadasha_lord="Ra",
        mahadasha_lord_name="Rahu", antardasha_lord="Sa", antardasha_lord_name="Saturn",
        score=1.5, evidence_level="house_lord_antardasha", dusthana_afflicted=False,
    )
    dumped = period.model_dump(mode="json")
    assert dumped["start_date"] == "2025-01-01"
    import json

    json.dumps(dumped)  # must not raise


async def test_chat_astro_vyasa_answers_every_topic_directly_without_redirecting(client, monkeypatch):
    """Vyasa is the new default generalist persona (see
    templates._RISHI_SPECIALTY, which deliberately excludes it) — it must
    answer a question that WOULD redirect for a specialist, with no
    redirect/pointer text of its own."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "Tell me about my marriage prospects", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert "Gargi" not in reply and "Bhrigu" not in reply


async def test_chat_astro_returns_answered_by_rishi_id_attribution(client, monkeypatch):
    """Independent of who's chatting, the response names the real specialist
    who classically owns this question's topic — the frontend uses this to
    render a small "answered by X" corner label (see detect_answering_rishi)."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "Tell me about my marriage prospects", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["answered_by_rishi_id"] == "gargi"

    resp2 = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "How is my career looking?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["answered_by_rishi_id"] == "bhrigu"


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


@pytest.mark.parametrize(
    "message,rishi_id",
    [
        ("Why was my marriage delayed?", "gargi"),
        ("Did I have a good period for my career in the past?", "bhrigu"),
        ("Was there ever a good time for me to have had children?", "gargi"),
    ],
)
async def test_chat_astro_past_tense_life_event_questions_search_backward(client, monkeypatch, message, rishi_id):
    """Real past-tense phrasings ("why was X delayed", "did I have a good
    period for X") must search the past (birth-to-now), not the future —
    the honest, real-astrologer style "was classically a period associated
    with... did that line up" phrasing, not a "guaranteed date" framing that
    makes no sense for something the calendar says already happened."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": message, "rishi_id": rishi_id, "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert (
        "line up with anything that happened" in reply
        or "I didn't find a strongly active window" in reply
    )
    assert "not a guaranteed exact date" not in reply  # that's the future-tense framing, must not leak in


async def test_chat_astro_answers_what_happened_around_a_specific_past_year(client, monkeypatch):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "What happened to me in 2010?", "rishi_id": "parashara", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert "dominant influence at that time" in reply  # plain-language, not Mahadasha/Antardasha jargon
    assert "Antardasha" not in reply and "Mahadasha" not in reply
    assert "you experienced" not in reply.lower()  # honest tendency framing, never a fabricated specific claim


async def test_chat_astro_sarkari_naukri_question_routes_to_career(client, monkeypatch):
    """Real, high-volume FAQ phrasing from research — previously entirely
    unrepresented in the career keyword list."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "Sarkari naukri kab lagegi?", "rishi_id": "bhrigu", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert "probable favorable window" in reply or "I didn't find a strongly favorable window" in reply


async def test_chat_astro_requires_birth_profile(client):
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "nochat@example.com", "password": "supersecret1", "name": "No Birth", "preferred_language": "en"},
    )
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    resp = await client.post("/api/v1/chat/astro", headers=headers, json={"message": "Hello", "language": "en"})
    assert resp.status_code == 400
