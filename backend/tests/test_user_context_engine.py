"""Coverage for app.services.user_context_engine — the intent-scoped view
over existing authoritative memory (see that module's docstring: "No
duplicate life store"). Split out of the original combined
test_native_intelligence.py so each new native-engine module has its own
dedicated test file.

Also exercises chat_memory_service.retrieve_native_turns in the same
scenario (cross-persona, cross-user scoping) since both are queried
together by chat.py to build one turn's context — see that function's own
docstring for why it needs no embeddings/provider call."""
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models.chat import ChatMessage
from app.db.models.user import User
from app.services import chat_memory_service, life_context_service, user_context_engine
from tests.test_api_e2e import _signup_and_set_birth_data


async def test_scoped_context_and_offline_retrieval_across_rishis(client):
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User))
        other = User(email="other@example.com")
        db.add(other)
        await db.flush()
        for owner, text, persona in (
            # Statements, not questions — retrieve_native_turns deliberately
            # excludes past questions (see native_understanding.is_question),
            # since a question isn't a "situation" to quote back later.
            (user.id, "I am thinking about changing my software job.", "bhrigu"),
            (user.id, "My sister is getting married soon.", "gargi"),
            (other.id, "I am thinking about changing my software job at SECRET company.", "vyasa"),
        ):
            db.add(ChatMessage(user_id=owner, role="user", content=text, language="en", rishi_id=persona))
        await db.commit()
        await life_context_service.upsert_fact(db, user.id, "family", "sister_name", "Private unrelated name", "high", "user_stated")
        await life_context_service.upsert_fact(db, user.id, "family", "financial_responsibilities", "support parents", "high", "user_stated")
        await life_context_service.upsert_fact(db, user.id, "career", "occupation", "developer", "high", "user_stated")
        result = await user_context_engine.retrieve(db, user.id, ["job_change_decision"])
        assert "sister_name" not in result["life_context"]["family"]
        assert "financial_responsibilities" in result["life_context"]["family"]
        assert await life_context_service.get_active_context(db, user.id, []) == {}
        retrieved = await chat_memory_service.retrieve_native_turns(db, user.id, ["career"], "my software job")
        assert len(retrieved) == 1
        assert "SECRET" not in str(retrieved)
        assert "software job" in retrieved[0]["text"]


async def test_retrieve_surfaces_full_goal_history_not_just_the_active_one(client):
    """Stage 2 — goals as a list: upsert_fact already preserves every
    distinct goal ever stated (marks the old one superseded, never deletes
    it) — retrieve() needs to actually surface that history for a category
    that includes the "goals" domain, not just the single active fact."""
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User))
        await life_context_service.upsert_fact(db, user.id, "goals", "top_goal", "save money", "high", "user_stated")
        await life_context_service.upsert_fact(db, user.id, "goals", "top_goal", "get promoted", "high", "user_stated")
        await db.commit()
        result = await user_context_engine.retrieve(db, user.id, ["career"])
        values = [h["value"] for h in result["goal_history"]]
        assert values == ["save money", "get promoted"]
        # A category with no "goals" domain mapping shouldn't pay for the
        # extra query at all.
        result2 = await user_context_engine.retrieve(db, user.id, ["siblings"])
        assert result2["goal_history"] == []
