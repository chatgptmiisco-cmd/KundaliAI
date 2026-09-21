"""Coverage for Phase 6's personalization/completeness score — a single
0-100 number built purely from already-stored Phases 1-5 signals (no new
astrology, no LLM) — see app.services.personalization_score_service.
"""
from datetime import date

from app.db.base import AsyncSessionLocal
from app.services import (
    important_date_service, life_context_service, personalization_score_service,
)
from tests.test_api_e2e import _signup_and_set_birth_data


async def _real_user_id(client) -> str:
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    return profile.json()["id"]


async def test_score_is_zero_with_no_signals_at_all(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        result = await personalization_score_service.get_personalization_score(db, user_id)
        assert result["score"] == 0
        assert result["domains_covered"] == 0
        assert result["life_state_fields_set"] == 0
        assert result["has_life_event"] is False
        assert result["has_important_date"] is False
        assert result["has_tracked_decision"] is False


async def test_domain_coverage_scales_the_50_point_bucket(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.upsert_fact(db, user_id, "career", "occupation", "engineer", "high", "user_stated")
        result = await personalization_score_service.get_personalization_score(db, user_id)
        assert result["domains_covered"] == 1
        assert result["domains_total"] == 8
        assert result["score"] == round(50 * (1 / 8))


async def test_each_flat_signal_adds_its_own_weight(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.add_event(db, user_id, "new_job", "started a new job", 2020)
        await important_date_service.add_important_date(db, user_id, "career", "review", date(2020, 1, 1))
        await life_context_service.upsert_decision(db, user_id, "job_change_decision", "thinking about it")

        result = await personalization_score_service.get_personalization_score(db, user_id)
        assert result["has_life_event"] is True
        assert result["has_important_date"] is True
        assert result["has_tracked_decision"] is True
        assert result["score"] == 30  # 10 + 10 + 10, no domains/life-state signal set


async def test_full_coverage_reaches_a_perfect_score(client):
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    await client.put(
        "/api/v1/user/profile/life-state", headers=headers,
        json={"marital_status": "married", "career_state": "employed", "business_state": "none"},
    )
    async with AsyncSessionLocal() as db:
        for domain in life_context_service.VALID_DOMAINS:
            await life_context_service.upsert_fact(db, user_id, domain, "some_key", "some value", "high", "user_stated")
        await life_context_service.add_event(db, user_id, "new_job", "started a new job", 2020)
        await important_date_service.add_important_date(db, user_id, "career", "review", date(2020, 1, 1))
        await life_context_service.upsert_decision(db, user_id, "job_change_decision", "thinking about it")

        result = await personalization_score_service.get_personalization_score(db, user_id)
        assert result["domains_covered"] == 8
        assert result["life_state_fields_set"] == 3
        assert result["score"] == 100


async def test_life_state_fields_scale_the_20_point_bucket(client):
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    await client.put("/api/v1/user/profile/life-state", headers=headers, json={"marital_status": "married"})

    async with AsyncSessionLocal() as db:
        result = await personalization_score_service.get_personalization_score(db, user_id)
        assert result["life_state_fields_set"] == 1
        assert result["life_state_fields_total"] == 3
        assert result["score"] == round(20 * (1 / 3))
