"""Coverage for /admin/metrics (product spec §20) — no admin test existed
before this, so this also exercises get_current_admin's 403 path for a
regular user for the first time."""
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models.chat import ChatMessage
from app.db.models.user import User
from app.services import life_context_service
from tests.test_api_e2e import _signup_and_set_birth_data


async def _make_admin(user_id: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one()
        user.is_admin = True
        await db.commit()


async def test_metrics_requires_admin(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/admin/metrics", headers=headers)
    assert resp.status_code == 403


async def test_metrics_reflects_seeded_data(client):
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]
    await _make_admin(user_id)

    async with AsyncSessionLocal() as db:
        await life_context_service.upsert_fact(db, user_id, "career", "occupation", "Engineer", "high", "user_stated")
        item = await life_context_service.upsert_fact(db, user_id, "money", "salary_range", "10-25L", "low", "inferred")
        await life_context_service.delete_fact(db, user_id, item.id)

        await life_context_service.upsert_decision(db, user_id, "job_change_decision", "lack of growth")
        decision = await life_context_service.mark_decision(db, user_id, "job_change_decision", "decided", "took new job")
        await life_context_service.record_outcome(db, user_id, decision.id, "better than expected")

        db.add(ChatMessage(
            user_id=user_id, role="assistant", content="a personalized reply",
            language="en", rishi_id="bhrigu", used_personalization=True,
        ))
        db.add(ChatMessage(
            user_id=user_id, role="assistant", content="a generic reply",
            language="en", rishi_id="bhrigu", used_personalization=False,
        ))
        await db.commit()

    resp = await client.get("/api/v1/admin/metrics", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["context_depth"]["total_active_facts"] == 1
    assert body["context_depth"]["users_with_at_least_one_fact"] == 1

    assert body["context_utilization"]["total_assistant_replies"] == 2
    assert body["context_utilization"]["replies_using_context"] == 1
    assert body["context_utilization"]["utilization_rate"] == 0.5

    assert body["correction_rate"]["total_facts_ever_recorded"] == 2
    assert body["correction_rate"]["user_deleted"] == 1
    assert body["correction_rate"]["correction_rate"] == 0.5

    assert body["outcome_capture"]["decisions_decided"] == 1
    assert body["outcome_capture"]["decisions_with_outcome"] == 1
    assert body["outcome_capture"]["outcome_capture_rate"] == 1.0
