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
from datetime import date, datetime, timedelta, timezone

import pytest

from app.api.v1 import chat as chat_module
from app.astro.dasha import Antardasha, Mahadasha
from app.core.config import Settings
from app.db.base import AsyncSessionLocal
from app.services import chat_memory_service, dasha_service, important_date_service, life_context_service
from app.services.chat_understanding import ChatUnderstanding
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


async def test_chat_astro_relocation_decision_answers_and_tracks_as_a_decision(client, monkeypatch):
    """Phase 3 (spec §56 "relocation decisions") — relocation_decision has no
    get_decision verdict engine behind it (see life_context_service._DECISION_
    TYPE_BY_CATEGORY's comment); it reuses the SAME foreign_travel life-event-
    timing engine as foreign_travel_timing. Exercises the real deterministic
    keyword path end-to-end (message_mentions_relocation_decision in
    templates.py -> chat.py's relocation block -> _life_event_chat_answer),
    not a monkeypatched classifier, and confirms it's tracked as a real
    Decision Memory row under decision_type "relocation" — the same
    generalized mapping outcome-checkins/gap-filling already read off."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers,
        json={"message": "Should I relocate abroad for work?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"]

    async with AsyncSessionLocal() as db:
        open_decisions = await life_context_service.get_open_decisions(db, user_id)
        assert any(d.decision_type == "relocation" for d in open_decisions)


async def test_chat_astro_decision_gap_question_gate_generalizes_to_relocation(client, monkeypatch):
    """The decision-critical gap-filling gate (chat.py, right after the
    classify_message call) checks `c in decision_known_facts_for_prompt for
    c in understanding.categories` — decision_known_facts_for_prompt is
    built generically off life_context_service.CATEGORY_BY_DECISION_TYPE's
    values, which now includes relocation_decision, so a crafted
    decision_gap_question for it should short-circuit the reply exactly like
    it already does for job_change_decision/business_start_decision, with
    zero relocation-specific code in this gate."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    async def _fake_classify_message(*args, **kwargs):
        return ChatUnderstanding(
            categories=["relocation_decision"],
            decision_gap_question="Is this move mainly for work, family, or lifestyle reasons?",
        )

    monkeypatch.setattr(chat_module, "classify_message", _fake_classify_message)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "Should I move abroad?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"] == "Is this move mainly for work, family, or lifestyle reasons?"


async def test_chat_astro_mentions_a_recurring_dasha_pattern_via_the_template_path(client, monkeypatch):
    """Phase 4 (spec's "richer correlations") — two of the user's OWN
    confirmed career events sharing a Mahadasha lord should surface as a
    real, deterministic sentence even on the template (non-LLM) path (see
    templates._personal_pattern_sentence), since it states a fact about
    their own recorded history, not an interpretive claim. Monkeypatches
    dasha_service.get_mahadashas_raw with a small fixed fixture for
    deterministic control (mirrors test_life_pattern_service.py)."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    async def _fake_mahadashas(*a, **k):
        return [
            Mahadasha(
                lord="Sa", start=datetime(2010, 1, 1, tzinfo=timezone.utc), end=datetime(2029, 1, 1, tzinfo=timezone.utc),
                antardashas=[
                    Antardasha(lord="Ve", start=datetime(2010, 1, 1, tzinfo=timezone.utc), end=datetime(2020, 1, 1, tzinfo=timezone.utc)),
                ],
            )
        ]
    monkeypatch.setattr(dasha_service, "get_mahadashas_raw", _fake_mahadashas)

    async with AsyncSessionLocal() as db:
        await life_context_service.add_event(db, user_id, "new_job", "started at Acme", 2011)
        await life_context_service.add_event(db, user_id, "promotion", "promoted", 2015)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "When will my career improve?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert "2 of your past events in this area happened during a" in reply


async def test_chat_astro_exposes_astrological_fingerprint_fields_in_context(client, monkeypatch):
    """Phase 4 (finishes spec §21, deferred from Phase 2) — compute_natal_
    insights is computed from the D1 chart chat.py already fetches (zero
    extra cost) and stored as strongest_planet/weakest_planet/decision_style
    always, plus blind_spot_planet/reason only when there's a real
    affliction to report. This isn't visible in the template reply (it's an
    LLM-prompt-only tone signal per the plan), so this test goes straight at
    chat_module.classify_message's own `current_life_state`-style plumbing
    isn't relevant here — instead it captures the context dict chat_reply
    receives by monkeypatching the interpreter's chat_reply."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    captured = {}

    async def _fake_chat_reply(self, history, context, language):
        captured.update(context)
        return "ok"

    from app.services.interpretation.templates import TemplateInterpreter
    monkeypatch.setattr(TemplateInterpreter, "chat_reply", _fake_chat_reply)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "How's my career looking?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert "decision_style" in captured
    assert captured["decision_style"] in (
        "fast_and_decisive", "steady_and_persistent", "adaptive_and_scattered", "impulsive_and_reactive",
    )
    # Either both blind_spot fields are present, or neither is — never one
    # without the other, and never invented when there's no real affliction.
    assert ("blind_spot_planet" in captured) == ("blind_spot_reason" in captured)


def _fake_natal_insights(*, debilitated_stress_planet: bool):
    """Phase 5 fix's fixture: a minimal but complete NatalInsights, varying
    only whether the stress_planet is genuinely debilitated (the real
    affliction chat.py's own severity recompute checks for) — every other
    field is a plausible placeholder, irrelevant to what's under test."""
    from app.astro.natal_insights import NatalInsights
    return NatalInsights(
        lagna_lord="Ma", lagna_lord_house=1, tenth_lord="Sa", tenth_lord_house=10,
        seventh_lord="Ve", seventh_lord_house=7, sixth_lord="Me", sixth_lord_house=6,
        planet_dignity={"Me": "debilitated" if debilitated_stress_planet else "neutral"},
        strongest_planet=None, weakest_planet="Me" if debilitated_stress_planet else None,
        house_lords={h: "Me" for h in range(1, 13)}, house_lord_houses={h: 6 for h in range(1, 13)},
        combust_planets=frozenset(), blind_spot_planet="Ma", blind_spot_reason="none",
        stress_house=6, stress_planet="Me", decision_style="steady_and_persistent",
    )


async def test_chat_astro_shows_stress_house_when_genuinely_afflicted(client, monkeypatch):
    """Phase 5 fix — stress_house/stress_planet are only ever exposed when
    chat.py's own severity recompute (from planet_dignity/combust_planets)
    finds a real affliction, never unconditionally like Phase 4 originally
    left them (which risked a forced "stress" narrative onto an
    unafflicted chart)."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    monkeypatch.setattr(chat_module, "compute_natal_insights", lambda *a, **k: _fake_natal_insights(debilitated_stress_planet=True))

    captured = {}

    async def _fake_chat_reply(self, history, context, language):
        captured.update(context)
        return "ok"

    from app.services.interpretation.templates import TemplateInterpreter
    monkeypatch.setattr(TemplateInterpreter, "chat_reply", _fake_chat_reply)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "How's my career looking?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert captured.get("stress_house") == 6
    assert captured.get("stress_planet")


async def test_chat_astro_omits_stress_house_when_not_afflicted(client, monkeypatch):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    monkeypatch.setattr(chat_module, "compute_natal_insights", lambda *a, **k: _fake_natal_insights(debilitated_stress_planet=False))

    captured = {}

    async def _fake_chat_reply(self, history, context, language):
        captured.update(context)
        return "ok"

    from app.services.interpretation.templates import TemplateInterpreter
    monkeypatch.setattr(TemplateInterpreter, "chat_reply", _fake_chat_reply)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "How's my career looking?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert "stress_house" not in captured
    assert "stress_planet" not in captured


async def test_chat_astro_house_purchase_decision_answers_and_tracks_as_a_decision(client, monkeypatch):
    """Phase 5 — house_purchase_decision is fully generic in get_decision
    (new EventType="property"), reusing the exact same _DECISION_CHECKS
    loop as job_change/business_start with zero new chat.py code. Exercises
    the real deterministic keyword path (message_mentions_house_purchase_
    decision) end to end, mirroring Phase 3's relocation_decision test."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "Should I buy a house right now?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"]

    async with AsyncSessionLocal() as db:
        open_decisions = await life_context_service.get_open_decisions(db, user_id)
        assert any(d.decision_type == "house_purchase" for d in open_decisions)


async def test_chat_astro_marriage_decision_answers_and_tracks_as_a_decision(client, monkeypatch):
    """Phase 5 — marriage_decision deliberately bypasses get_decision (see
    prediction_service.get_marriage_decision's docstring), but is tracked as
    a Decision Memory row exactly like the get_decision-backed types.
    Exercises the real deterministic keyword path (message_mentions_
    marriage_decision, reusing the plain "marriage" topic's own keyword
    list) end to end."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "Should I get married now?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"]

    async with AsyncSessionLocal() as db:
        open_decisions = await life_context_service.get_open_decisions(db, user_id)
        assert any(d.decision_type == "marriage" for d in open_decisions)


async def test_chat_astro_important_date_checkin_resolves_and_creates_a_life_event(client, monkeypatch):
    """Phase 5 — a real important-date check-in resolved via a crafted
    ChatUnderstanding.important_date_outcome (classify_message itself needs
    a real OpenAI call the test environment deliberately disables) creates
    a real LifeEvent — mirrors Phase 2's test_chat_resolves_pending_
    feedback_and_creates_a_life_event."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    past_date = date.today() - timedelta(days=5)
    async with AsyncSessionLocal() as db:
        await important_date_service.add_important_date(db, user_id, "career", "final exam", past_date)

    async def _fake_classify_message(*args, **kwargs):
        return ChatUnderstanding(categories=[], important_date_outcome="I passed the exam")

    monkeypatch.setattr(chat_module, "classify_message", _fake_classify_message)

    # Turn 1: a brand-new conversation deterministically leads with the
    # check-in question itself (see chat.py's "not history_rows" gate) —
    # classify_message is never even called on this turn.
    first = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": "hi", "language": "en"},
    )
    assert first.status_code == 200, first.text
    assert "final exam" in first.json()["reply"]

    # Turn 2: now history_rows is non-empty, so this reaches the real
    # classify_message call (monkeypatched above).
    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "It went well, I passed", "language": "en"},
    )
    assert resp.status_code == 200, resp.text

    async with AsyncSessionLocal() as db:
        pending = await important_date_service.get_pending_checkin(db, user_id)
        assert pending is None  # resolved, no longer pending

        timeline = await life_context_service.get_timeline(db, user_id)
        assert any(e["description"] == "I passed the exam" for e in timeline)


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
    if "promotion" in message:
        # career_promotion_timing is gated on career_state == "employed" —
        # see test_career_promotion_timing_is_gated_by_career_state in
        # test_api_e2e.py for the gate itself; this test is about the
        # real-engine reply shape once that precondition is met, same as
        # every other category here.
        await client.put("/api/v1/user/profile/life-state", headers=headers, json={"career_state": "employed"})

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": message, "rishi_id": rishi_id, "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert "probable favorable window" in reply or "I didn't find a strongly favorable window" in reply


async def test_chat_astro_promotion_question_asks_about_employment_before_answering(client, monkeypatch):
    """Without a known career_state, a promotion question must not silently
    assume the user has a job to be promoted in — the reply should surface
    the career_promotion_blocked note (see prediction_service.
    get_life_event_timing) instead of a full dasha-window analysis."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro",
        headers=headers, json={"message": "When will I get a promotion?", "rishi_id": "bhrigu", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert "currently employed" in reply
    assert "probable favorable window" not in reply


async def test_chat_astro_replying_yes_to_the_employment_gate_answers_same_turn(client, monkeypatch):
    """The exact dead-end a real user hit: the fallback (no-LLM) path can't
    turn a bare "yes" into a life_state_update on its own (see chat.py's
    _asked_career_employment_gate handling), so without a deterministic
    fallback the conversation fell through to the generic Lagna/menu reply
    instead of ever answering the original question. A plain "yes" right
    after the gate note must set career_state=employed AND give the real
    promotion-timing analysis in that SAME reply — not require yet another
    message."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    gated = await client.post(
        "/api/v1/chat/astro",
        headers=headers, json={"message": "When will I get a promotion?", "rishi_id": "bhrigu", "language": "en"},
    )
    assert "currently employed" in gated.json()["reply"]

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": "yes", "rishi_id": "bhrigu", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert "probable favorable window" in reply
    assert "Your Lagna is" not in reply

    profile = await client.get("/api/v1/user/profile", headers=headers)
    assert profile.json()["life_state"]["career_state"] == "employed"


async def test_chat_astro_replying_no_to_the_employment_gate_is_acknowledged(client, monkeypatch):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    await client.post(
        "/api/v1/chat/astro",
        headers=headers, json={"message": "When will I get a promotion?", "rishi_id": "bhrigu", "language": "en"},
    )
    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": "no", "rishi_id": "bhrigu", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert "no worries" in resp.json()["reply"]

    profile = await client.get("/api/v1/user/profile", headers=headers)
    assert profile.json()["life_state"]["career_state"] == "unemployed"


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


async def test_chat_astro_surfaces_retrieved_history_into_context(client, monkeypatch):
    """See app.services.chat_memory_service — older conversation context
    that fell out of the raw history window must reach the reply-
    generating context under "retrieved_history", the same way
    life_context/open_decisions already do (see openai_interpreter.py's
    retrieved_history_line)."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    canned = [{"text": "User: I work at a startup.\nAssistant: noted.", "when": "3 months ago"}]

    async def _fake_retrieve(*args, **kwargs):
        return canned

    monkeypatch.setattr(chat_memory_service, "retrieve_relevant_turns", _fake_retrieve)

    captured = {}

    async def _fake_chat_reply(self, history, context, language):
        captured.update(context)
        return "ok"

    from app.services.interpretation.templates import TemplateInterpreter
    monkeypatch.setattr(TemplateInterpreter, "chat_reply", _fake_chat_reply)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": "how's my job going", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert captured.get("retrieved_history") == canned


async def test_chat_astro_embeds_the_assistant_reply_when_embedding_succeeds(client, monkeypatch):
    from app.db.models.chat import ChatMessage
    from sqlalchemy import select

    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    async def _fake_embed_turn(user_message, assistant_reply):
        return [0.1, 0.2, 0.3], f"User: {user_message}\nAssistant: {assistant_reply}"

    monkeypatch.setattr(chat_memory_service, "embed_turn", _fake_embed_turn)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": "How's my career looking?", "language": "en"},
    )
    assert resp.status_code == 200, resp.text

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatMessage).where(ChatMessage.role == "assistant").order_by(ChatMessage.id.desc()).limit(1)
        )
        row = result.scalar_one()
        assert row.embedding == "[0.1, 0.2, 0.3]"
        assert row.embedding_source_text is not None and "How's my career looking?" in row.embedding_source_text


async def test_chat_astro_embedding_failure_leaves_the_row_unembedded_but_still_replies(client, monkeypatch):
    from app.db.models.chat import ChatMessage
    from sqlalchemy import select

    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    async def _fake_embed_turn(user_message, assistant_reply):
        return None

    monkeypatch.setattr(chat_memory_service, "embed_turn", _fake_embed_turn)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": "How's my career looking?", "language": "en"},
    )
    assert resp.status_code == 200, resp.text

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatMessage).where(ChatMessage.role == "assistant").order_by(ChatMessage.id.desc()).limit(1)
        )
        row = result.scalar_one()
        assert row.embedding is None
        assert row.embedding_source_text is None
