"""Coverage for Phase 7's adaptive multi-session onboarding signal — "what's
the most useful thing to ask this user next," computed purely from Phases
1-6's own already-stored data (no new tables, no LLM) — see
app.services.onboarding_followup_service.
"""
from datetime import datetime, timedelta, timezone

from app.db.base import AsyncSessionLocal
from app.services import life_context_service, onboarding_followup_service
from tests.test_api_e2e import _signup_and_set_birth_data

_OLD_ENOUGH = datetime.now(timezone.utc) - timedelta(days=10)
_TOO_YOUNG = datetime.now(timezone.utc)


async def _real_user_id(client) -> str:
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    return profile.json()["id"]


async def test_returns_none_for_a_brand_new_account_with_no_signals(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        result = await onboarding_followup_service.get_next_onboarding_topic(db, user_id, _TOO_YOUNG)
        assert result is None


async def test_life_event_trigger_fires_for_an_uncovered_mapped_domain(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.add_event(db, user_id, "new_job", "started at Acme", 2020)
        # Account too young for the time-based fallback — this must be the
        # life_event trigger specifically, not a coincidental time-based hit.
        result = await onboarding_followup_service.get_next_onboarding_topic(db, user_id, _TOO_YOUNG)
        assert result == {"topic": "career", "reason": "life_event"}


async def test_life_event_trigger_is_silent_once_the_domain_is_covered(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.add_event(db, user_id, "new_job", "started at Acme", 2020)
        await life_context_service.upsert_fact(db, user_id, "career", "employer", "Acme", "high", "user_stated")
        result = await onboarding_followup_service.get_next_onboarding_topic(db, user_id, _TOO_YOUNG)
        assert result is None  # too young for time-based, and career is now covered


async def test_life_event_with_an_unmapped_type_does_not_trigger(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.add_event(db, user_id, "moved_city", "relocated", 2020)
        result = await onboarding_followup_service.get_next_onboarding_topic(db, user_id, _TOO_YOUNG)
        assert result is None


async def test_time_based_fallback_requires_a_sufficiently_old_account(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        too_young = await onboarding_followup_service.get_next_onboarding_topic(db, user_id, _TOO_YOUNG)
        assert too_young is None

        old_enough = await onboarding_followup_service.get_next_onboarding_topic(db, user_id, _OLD_ENOUGH)
        assert old_enough is not None
        assert old_enough["reason"] == "time_based"
        assert old_enough["topic"] in (
            "career", "business", "relationships", "marriage", "money", "family", "personal_direction", "other",
        )


async def test_time_based_fallback_returns_none_once_every_mapped_topic_is_covered(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        for domain in {"career", "business", "relationships", "money", "family", "goals", "preferences"}:
            await life_context_service.upsert_fact(db, user_id, domain, "some_key", "some value", "high", "user_stated")
        result = await onboarding_followup_service.get_next_onboarding_topic(db, user_id, _OLD_ENOUGH)
        assert result is None


async def test_life_event_trigger_takes_priority_over_time_based(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        # Cover everything except "family" via a life event, then check an
        # OLD-ENOUGH account still reports the life_event reason for family
        # specifically (not some other uncovered topic the time-based path
        # would have picked first by dict order).
        for domain in {"career", "business", "relationships", "money", "goals", "preferences"}:
            await life_context_service.upsert_fact(db, user_id, domain, "some_key", "some value", "high", "user_stated")
        await life_context_service.add_event(db, user_id, "became_parent", "had a baby", 2021)
        result = await onboarding_followup_service.get_next_onboarding_topic(db, user_id, _OLD_ENOUGH)
        assert result == {"topic": "family", "reason": "life_event"}
