"""Coverage for Phase 5's important-dates/goal-target-dates feature: a real
future date the user mentioned, checked back on once it passes (no push/
scheduling infra exists, so this reuses the same "pull on next request"
convention as outcome check-ins/context decay) — see
app.services.important_date_service.
"""
from datetime import date, timedelta

from app.db.base import AsyncSessionLocal
from app.services import important_date_service, life_context_service
from tests.test_api_e2e import _signup_and_set_birth_data


async def _real_user_id(client) -> str:
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    return profile.json()["id"]


async def test_add_important_date_defaults_an_invalid_domain_to_goals(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        row = await important_date_service.add_important_date(
            db, user_id, "not_a_real_domain", "save $10k", date.today() + timedelta(days=90)
        )
        assert row.domain == "goals"


async def test_get_pending_checkin_ignores_a_future_date(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await important_date_service.add_important_date(
            db, user_id, "career", "future exam", date.today() + timedelta(days=30)
        )
        assert await important_date_service.get_pending_checkin(db, user_id) is None


async def test_get_pending_checkin_promotes_and_returns_a_passed_date(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        added = await important_date_service.add_important_date(
            db, user_id, "career", "final exam", date.today() - timedelta(days=3)
        )
        assert added.status == "pending"

        pending = await important_date_service.get_pending_checkin(db, user_id)
        assert pending is not None
        assert pending.id == added.id
        assert pending.status == "passed_unconfirmed"

        # Idempotent — calling again finds the same already-promoted row,
        # not a fresh promotion or a duplicate.
        again = await important_date_service.get_pending_checkin(db, user_id)
        assert again.id == added.id


async def test_get_pending_checkin_returns_the_oldest_when_several_have_passed(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        older = await important_date_service.add_important_date(
            db, user_id, "career", "older deadline", date.today() - timedelta(days=10)
        )
        await important_date_service.add_important_date(
            db, user_id, "money", "newer deadline", date.today() - timedelta(days=2)
        )
        pending = await important_date_service.get_pending_checkin(db, user_id)
        assert pending.id == older.id


async def test_resolve_important_date_sets_resolved_and_creates_a_life_event(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        added = await important_date_service.add_important_date(
            db, user_id, "career", "final exam", date(2020, 6, 15)
        )
        resolved = await important_date_service.resolve_important_date(db, user_id, added.id, "I passed with honors")
        assert resolved.status == "resolved"
        assert resolved.resolved_at is not None

        timeline = await life_context_service.get_timeline(db, user_id)
        assert any(
            e["description"] == "I passed with honors" and e["year"] == 2020 and e["month"] == 6
            for e in timeline
        )


async def test_resolve_important_date_without_a_description_skips_the_life_event(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        added = await important_date_service.add_important_date(
            db, user_id, "career", "final exam", date(2021, 1, 1)
        )
        await important_date_service.resolve_important_date(db, user_id, added.id, None)
        timeline = await life_context_service.get_timeline(db, user_id)
        assert timeline == []


async def test_resolve_important_date_returns_none_for_a_nonexistent_row(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        assert await important_date_service.resolve_important_date(db, user_id, 999999, "x") is None
