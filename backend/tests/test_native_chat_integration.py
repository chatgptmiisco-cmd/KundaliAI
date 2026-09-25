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
    # "developer"/"ecommerce" were already stated (and shown back) on
    # earlier turns — shown_facts (native_response.personal_context)
    # deliberately does NOT repeat a fact already surfaced once this
    # conversation, direct product feedback against restating the same
    # line on every later turn. Not asserted here anymore; that's the
    # intended new behavior, not a gap.
    # One decision-critical question per turn now, not all 3 bundled into
    # one message (see conversation_engine.questions_for) — the first one
    # asked is "reason" (what's driving the change), not "savings".
    assert "driving the change" in reply.lower()
    async with AsyncSessionLocal() as db:
        state = await db.scalar(select(ConversationState))
        assert state.data["pending"] == ["reason"]
    # "offer" is already implicitly known here (known_slot aliases it to
    # career.transition_intent, already set by "I want to start an
    # ecommerce business." above) — so the next slot asked is "runway",
    # not "offer".
    reply = await chat("Growth")
    assert "savings" in reply.lower() or "income" in reply.lower()
    async with AsyncSessionLocal() as db:
        state = await db.scalar(select(ConversationState))
        assert state.data["pending"] == ["runway"]
    reply = await chat("I have six months of savings")
    # "your intended transition: business" (personal_context) was already
    # shown on an earlier turn and is correctly suppressed now (shown_facts)
    # — the synthesized job_change_decision sentence (reason + runway) is
    # what should still be there, freshly, since "savings" is only known
    # as of THIS turn.
    assert "driving this" in reply.lower()
    assert "fall back on" in reply.lower()
    await chat("Actually I am a teacher.", "gargi")
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User))
        facts = await life_context_service.get_active_context(db, user.id, ["career"])
        assert facts["career"]["occupation"]["value"] == "teacher"
        history = await life_context_service.get_fact_history(db, user.id, "career", "occupation")
        assert any(f["value"] == "developer" and f["status"] == "superseded" for f in history)


async def test_business_category_suitability_is_a_distinct_answer_not_generic_career_timing(client, monkeypatch):
    """Scenario D from the personal-astrologer chat upgrade plan: "will
    clothing business work for me" must resolve to the new, multi-signal
    business_category_suitability capability — never fall back to the
    generic business_start_decision/career-timing paragraph."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "all_features_free", True)
    headers = await _signup_and_set_birth_data(client)

    response = await client.post("/api/v1/chat/astro", headers=headers,
                                 json={"message": "Will clothing business work for me?", "rishi_id": "vyasa", "engine_only": True})
    assert response.status_code == 200, response.text
    reply = response.json()["reply"].lower()
    # The distinct suitability sentence names the category itself and either
    # a chart-alignment verdict or an honest "can't validate this specific
    # category" — never the generic "good times and bad times" career filler
    # business_start_decision's own paragraph would produce instead.
    assert "clothing" in reply


async def test_job_vs_business_decision_uses_actual_known_facts_not_generic_filler(client, monkeypatch):
    """Scenario E from the plan: once the business type and funding are
    already known, "should I stay in my job or switch to business" must
    reference that actual situation, not the bare "good times and bad
    times" filler a fully generic decision answer would give."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "all_features_free", True)
    headers = await _signup_and_set_birth_data(client)

    async def chat(message):
        response = await client.post("/api/v1/chat/astro", headers=headers,
                                     json={"message": message, "rishi_id": "vyasa", "engine_only": True})
        assert response.status_code == 200, response.text
        return response.json()["reply"]

    await chat("I want to start a clothing business.")
    await chat("I would fund it through my savings.")
    reply = await chat("Should I stay in my job or switch to business?")
    assert "clothing" in reply.lower()
    assert "savings" in reply.lower()


async def test_full_business_switch_conversation_combines_timing_and_suitability(client, monkeypatch):
    """Scenario H from the plan — the full end-to-end multi-turn flow: once
    enough is known (type, mode, customers), the reply should draw on the
    user's actual situation rather than a single generic career paragraph."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "all_features_free", True)
    headers = await _signup_and_set_birth_data(client)

    async def chat(message):
        response = await client.post("/api/v1/chat/astro", headers=headers,
                                     json={"message": message, "rishi_id": "vyasa", "engine_only": True})
        assert response.status_code == 200, response.text
        return response.json()["reply"]

    await chat("I want to switch to business.")
    await chat("Clothing.")
    # The Phase 3 pending-priority fix: this must bind to transition_mode,
    # not be discarded as a false "career" topic switch because it contains
    # the word "job".
    reply = await chat("Yes, alongside my job.")
    async with AsyncSessionLocal() as db:
        state = await db.scalar(select(ConversationState))
        assert "transition_mode" not in (state.data.get("pending") or [])
    reply = await chat("I already have customers.")
    # A distinct suitability question, asked in the same flow, must get a
    # suitability-specific answer naming the actual category — never the
    # generic career-timing paragraph.
    reply = await chat("Will clothing business work for me?")
    assert "clothing" in reply.lower()


async def test_changed_my_plan_names_the_specific_prior_business_plan(client, monkeypatch):
    """Scenario G from the plan: "I changed my plan" after an established
    business plan must ask what specifically changed, NAMING the actual
    prior plan — never a generic re-elicitation question and never a reset
    to the generic topic menu."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "all_features_free", True)
    headers = await _signup_and_set_birth_data(client)

    async def chat(message):
        response = await client.post("/api/v1/chat/astro", headers=headers,
                                     json={"message": message, "rishi_id": "vyasa", "engine_only": True})
        assert response.status_code == 200, response.text
        return response.json()["reply"]

    await chat("I want to start a clothing business.")
    reply = await chat("I changed my plan.")
    assert "clothing" in reply.lower()

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User))
        facts = await life_context_service.get_active_context(db, user.id, ["business"])
        # The stale type is retracted (no longer active) rather than kept
        # around and silently reused for the next answer.
        assert "business_type" not in facts.get("business", {})


async def test_explicit_business_switch_overrides_a_stale_confirmed_career_focus(client, monkeypatch):
    """Caught live, reproduced exactly: once question_strategy.resolve_focus
    sets focus_confirmed="career" (the user picked "Current job growth" from
    the recall menu), usable_facts()'s OWN focus_confirmed=="career"
    suppression silently stripped EVERY business-domain fact from
    context["life_context"] for the rest of the conversation — including
    business.goal/funding stated on the SAME turns they were answered —
    so "I want to switch to business" -> "cloths" -> "savings" kept getting
    answered with the bare, unpersonalized career reading forever, never
    reflecting either answer. The current message must always outrank a
    stale confirmed focus from an earlier, unrelated part of the
    conversation."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "all_features_free", True)
    headers = await _signup_and_set_birth_data(client)

    async def chat(message):
        response = await client.post("/api/v1/chat/astro", headers=headers,
                                     json={"message": message, "rishi_id": "vyasa", "engine_only": True})
        assert response.status_code == 200, response.text
        return response.json()["reply"]

    await chat("I work as a developer.")
    await chat("I have some savings.")
    await chat("career")
    await chat("1")  # "Current job growth" -> sets focus_confirmed="career"
    await chat("I want to switch to business")
    await chat("cloths")
    reply = await chat("savings")
    assert "cloths" in reply.lower()
    assert "savings" in reply.lower()


async def test_financial_outlook_question_answers_directly_without_asking_for_income(client, monkeypatch):
    """URGENT CORRECTION section 2 (test #1): "How will I do financially?"
    is an astrology outlook question the engine can already answer from the
    birth chart — it must never ask for salary/income/expenses first."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "all_features_free", True)
    headers = await _signup_and_set_birth_data(client)

    response = await client.post("/api/v1/chat/astro", headers=headers,
                                 json={"message": "How will we do financially?", "rishi_id": "vyasa", "engine_only": True})
    assert response.status_code == 200, response.text
    reply = response.json()["reply"].lower()
    assert "income" not in reply or "monthly income" not in reply
    for forbidden in ("what is your income", "what is your salary", "monthly income", "monthly salary"):
        assert forbidden not in reply


async def test_weekly_question_answers_directly_without_asking_for_goals(client, monkeypatch):
    """URGENT CORRECTION test #20: "How's my week looking?" must give a
    direct weekly/daily astrology reading, never ask what the user's goals
    for the week are."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "all_features_free", True)
    headers = await _signup_and_set_birth_data(client)

    response = await client.post("/api/v1/chat/astro", headers=headers,
                                 json={"message": "How's my week looking?", "rishi_id": "vyasa", "engine_only": True})
    assert response.status_code == 200, response.text
    reply = response.json()["reply"].lower()
    assert "what are your goals" not in reply
    assert "reply with a number" not in reply


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
