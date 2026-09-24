from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models.life_context import LifeContextItem
from app.db.models.user import User
from app.db.models.chat import ChatMessage
from app.services import chat_memory_service
from app.services import question_strategy as strategy, life_context_service
from app.services.chat_understanding import ChatUnderstanding
from tests.test_api_e2e import _signup_and_set_birth_data
from tests.test_chat import _unlock_strategy_tier


@pytest.mark.parametrize("age,status,expected", [(0, "active", "ACTIVE"), (8, "active", "RECENT"), (31, "active", "HISTORICAL"), (0, "inactive", "INACTIVE")])
def test_memory_relevance(age, status, expected):
    now = datetime.now(timezone.utc)
    assert life_context_service.memory_relevance(status, now - timedelta(days=age), now) == expected


@pytest.mark.parametrize("message,categories,expected", [
    ("career", ["career"], "clarification"),
    ("Tell me about my career", ["career"], "clarification"),
    ("Should I start a business?", ["business_start_decision"], "decision"),
    ("When will my career improve?", ["career"], "prediction"),
    ("I have no growth at work", ["career"], "problem"),
    ("Is this still suitable?", ["career"], "confirmation"),
    ("Explain my chart", [], "information"),
])
def test_question_types(message, categories, expected):
    assert strategy.question_type(message, categories) == expected


@pytest.mark.parametrize("category,domain,key,value", [
    ("career", "business", "business_type", "steel and sanitary"),
    ("marriage", "relationships", "main_concern", "frequent fights"),
    ("money", "money", "main_concern", "loan repayments"),
    ("family", "family", "main_concern", "family disagreement"),
    ("business", "business", "business_type", "retail"),
])
def test_broad_topics_check_memory(category, domain, key, value):
    context = {"life_context": {domain: {key: {"id": "fact", "value": value, "relevance": "ACTIVE"}}}}
    state = {}
    reply = strategy.relevance_question(category, [category], context, state, "en", [])
    assert "previously" in reply and value in reply
    assert state["focus_pending"]["domain"] == category


@pytest.mark.parametrize("reply", ["2", "yes, relationship growth"])
def test_alternative_relationship_focus_does_not_reconfirm_old_fights(reply):
    context = {"life_context": {"relationships": {"main_concern": {"id": 1, "value": "frequent fights", "relevance": "HISTORICAL"}}}}
    state = {}
    strategy.relevance_question("marriage", ["marriage"], context, state, "en", [])
    understanding = ChatUnderstanding(categories=[])
    confirmed, _ = strategy.resolve_focus(understanding, reply, state, "en")
    assert not confirmed
    assert strategy.relevance_question("2", understanding.categories, context, state, "en", []) is None
    assert strategy.usable_facts(context, state, []) == {}


def test_resolving_a_recall_focus_suppresses_conversation_engines_own_menu_too():
    """Regression guard for a real, reproduced bug: picking "A current
    family concern" from relevance_question's recall menu resolves to the
    bare "family" category (FOCUS_OPTIONS["family"][0]) — but conversation_
    engine.questions_for() has its OWN "family" menu gate for a bare
    mention with nothing known yet, and it fired again immediately after,
    showing the user two different clarifying menus back to back for one
    simple message. resolve_focus must set family_clarified (and
    money_clarified) the same way it already set career_clarified/
    marriage_clarified, so questions_for()'s own gate is suppressed once a
    focus here is confirmed."""
    from app.services.conversation_engine import questions_for

    context = {"life_context": {"relationships": {"concern_type": {"id": 1, "value": "frequent fights", "relevance": "ACTIVE"}}}}
    state = {}
    strategy.relevance_question("family", ["family"], context, state, "en", [])
    understanding = ChatUnderstanding(categories=[])
    strategy.resolve_focus(understanding, "1", state, "en")
    assert understanding.categories == ["family"]
    assert state["family_clarified"] is True
    assert questions_for(["family"], {}, {}, state, "en") is None


def test_relationship_status_is_never_offered_as_a_recall_candidate():
    """Regression guard for a real, reproduced bug: "relationship" as a bare
    substring in the memory-key filter only ever matches "relationship_
    status" in this app's vocabulary — a plain marital-status fact, not a
    stated plan/concern — so it got surfaced as "you previously mentioned:
    married, is that still relevant?", crowding out the actual concern
    (concern_type) that should have been recalled instead."""
    context = {"life_context": {"relationships": {
        "relationship_status": {"id": 1, "value": "married", "relevance": "ACTIVE"},
        "concern_type": {"id": 2, "value": "frequent fights or arguments", "relevance": "ACTIVE"},
    }}}
    state = {}
    reply = strategy.relevance_question("relationship", ["marriage"], context, state, "en", [])
    assert "married" not in reply
    assert "frequent fights or arguments" in reply


def test_natural_denial_naming_the_remembered_fact_is_recognized_as_a_rejection():
    """Regression guard for a real, reproduced bug: "but its not about
    fights" matched none of the fixed reject phrases ("no longer"/"not
    anymore"/"abandoned"/...), so neither confirm nor reject fired,
    focus_pending was never cleared, and the SAME remembered "fights"
    concern kept resurfacing turn after turn even after the user explicitly
    said it was wrong. A negation word ("not"/"nahi") co-occurring with a
    real word from the remembered fact's own text (here "fights", from
    "frequent fights or arguments") must be recognized as a rejection —
    the user naming the specific thing they're denying is itself strong
    evidence, not just a fixed phrase list."""
    context = {"life_context": {"relationships": {"concern_type": {
        "id": 1, "value": "frequent fights or arguments", "relevance": "ACTIVE",
    }}}}
    state = {}
    strategy.relevance_question("relationship", ["marriage"], context, state, "en", [])
    assert state["focus_pending"]

    understanding = ChatUnderstanding(categories=[])
    confirmed, inactive = strategy.resolve_focus(understanding, "but its not about fights", state, "en")
    assert not confirmed
    assert inactive and inactive[0]["value"] == "frequent fights or arguments"
    assert "focus_pending" not in state
    assert understanding.categories == ["marriage"]


def test_confirmed_focus_expires():
    state = {"focus_confirmed": "career", "confirmed_fact_ids": [1], "focus_confirmed_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
    strategy.resolve_focus(ChatUnderstanding(categories=["career"]), "career", state, "en")
    assert "confirmed_fact_ids" not in state


async def seed_business(client, monkeypatch):
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User))
        fact = await life_context_service.upsert_fact(db, user.id, "business", "business_type", "steel and sanitary", "high", "user_stated")
        fact.last_confirmed_at = datetime.now(timezone.utc) - timedelta(days=60)
        await db.commit()
    return headers


async def ask(client, headers, message):
    response = await client.post("/api/v1/chat/astro", headers=headers, json={"message": message, "language": "en", "engine_only": True})
    assert response.status_code == 200, response.text
    return response.json()


async def test_old_business_does_not_choose_current_career_focus(client, monkeypatch):
    headers = await seed_business(client, monkeypatch)
    response = await ask(client, headers, "career")
    assert "previously" in response["reply"]
    assert "steel and sanitary" in response["reply"]
    assert "Current job growth" in response["reply"]
    assert response["question_type"] == "clarification"
    response = await ask(client, headers, "1")
    assert "job-versus-business" not in response["reply"]
    assert "steel and sanitary" not in response["reply"]


async def test_confirmed_business_gets_comparison_and_questions(client, monkeypatch):
    headers = await seed_business(client, monkeypatch)
    await ask(client, headers, "career")
    response = await ask(client, headers, "3")
    assert response["question_type"] == "decision"
    assert "steel and sanitary" in response["reply"]
    # The fixed "Compare three options... Next steps: speak with potential
    # customers and suppliers..." checklist (identical for every business_
    # start_decision reply regardless of the person) was removed per direct
    # feedback — real content (the stated business idea, the computed
    # timing, DECISION_SLOTS' own follow-up questions) already carries the
    # substance; this just asserts that generic block is gone.
    assert "Compare three options" not in response["reply"]
    async with AsyncSessionLocal() as db:
        fact = await db.scalar(select(LifeContextItem).where(LifeContextItem.key == "business_type"))
        assert fact.source == "user_confirmed"


async def test_rejected_memory_becomes_inactive(client, monkeypatch):
    headers = await seed_business(client, monkeypatch)
    await ask(client, headers, "career")
    response = await ask(client, headers, "no longer relevant")
    assert "inactive" in response["reply"]
    async with AsyncSessionLocal() as db:
        fact = await db.scalar(select(LifeContextItem).where(LifeContextItem.key == "business_type"))
        assert fact.status == "inactive"
        db.add(ChatMessage(user_id=fact.user_id, role="user", content="I plan to start a steel and sanitary business", language="en", rishi_id="bhrigu"))
        await db.commit()
        quotes = await chat_memory_service.retrieve_native_turns(db, fact.user_id, ["career"], "career")
        assert not any("steel and sanitary" in quote["text"] for quote in quotes)
    response = await ask(client, headers, "career")
    assert "steel and sanitary" not in response["reply"]


async def test_natural_denial_is_also_rejected_end_to_end(client, monkeypatch):
    """Same as test_rejected_memory_becomes_inactive above, but with the
    natural phrasing a real user actually typed live ("but its not about
    fights") instead of the fixed "no longer relevant" phrase — regression
    guard for the exact reproduced bug: this used to match neither confirm
    nor reject, so the same remembered fact kept resurfacing every turn."""
    headers = await seed_business(client, monkeypatch)
    await ask(client, headers, "career")
    response = await ask(client, headers, "but its not about steel and sanitary")
    assert "inactive" in response["reply"]
    async with AsyncSessionLocal() as db:
        fact = await db.scalar(select(LifeContextItem).where(LifeContextItem.key == "business_type"))
        assert fact.status == "inactive"
