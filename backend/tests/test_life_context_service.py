"""Direct coverage for app.services.life_context_service — the structured,
progressively-built personalization memory (Life Context Capture spec).
Uses the real test DB (via the `client` fixture's table setup) with a real
signed-up user for the FK, then exercises the service functions directly
with a raw session rather than through the chat endpoint, since AI is off
in this test environment and the chat classifier's real extraction is an
LLM call this suite deliberately never makes (see conftest.py)."""
from datetime import datetime, timedelta, timezone

from app.db.base import AsyncSessionLocal
from app.services import life_context_service
from tests.test_api_e2e import _signup_and_set_birth_data


async def _real_user_id(client) -> str:
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    assert profile.status_code == 200, profile.text
    return profile.json()["id"]


async def test_upsert_fact_creates_a_new_active_fact(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        item = await life_context_service.upsert_fact(
            db, user_id, "career", "occupation", "Software Engineer", "high", "user_stated"
        )
        assert item.status == "active"
        assert item.value == "Software Engineer"

        active = await life_context_service.get_active_context(db, user_id, ["career"])
        assert active == {
            "career": {
                "occupation": {
                    "value": "Software Engineer", "confidence": "high", "source": "user_stated",
                    "last_confirmed_at": active["career"]["occupation"]["last_confirmed_at"],
                }
            }
        }


async def test_upsert_fact_restating_the_same_value_does_not_duplicate(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.upsert_fact(db, user_id, "career", "employer", "TCS", "high", "user_stated")
        await life_context_service.upsert_fact(db, user_id, "career", "employer", "TCS", "high", "user_stated")

        history = await life_context_service.get_fact_history(db, user_id, "career", "employer")
        assert len(history) == 1


async def test_upsert_fact_confidence_can_only_be_upgraded_not_downgraded(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.upsert_fact(db, user_id, "career", "employer", "TCS", "low", "inferred")
        # Same value restated with higher confidence — should upgrade.
        item = await life_context_service.upsert_fact(db, user_id, "career", "employer", "TCS", "high", "user_confirmed")
        assert item.confidence == "high"
        assert item.source == "user_confirmed"

        # Same value again with LOWER confidence — must not downgrade.
        item = await life_context_service.upsert_fact(db, user_id, "career", "employer", "TCS", "low", "inferred")
        assert item.confidence == "high"


async def test_upsert_fact_with_a_new_value_supersedes_and_preserves_history(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.upsert_fact(db, user_id, "money", "salary_range", "₹10-25L", "high", "user_stated")
        await life_context_service.upsert_fact(db, user_id, "money", "salary_range", "₹25-50L", "high", "user_stated")

        active = await life_context_service.get_active_context(db, user_id, ["money"])
        assert active["money"]["salary_range"]["value"] == "₹25-50L"

        history = await life_context_service.get_fact_history(db, user_id, "money", "salary_range")
        assert [h["value"] for h in history] == ["₹10-25L", "₹25-50L"]
        assert [h["status"] for h in history] == ["superseded", "active"]


async def test_get_active_context_excludes_deleted_and_filters_by_domain(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        career_item = await life_context_service.upsert_fact(
            db, user_id, "career", "occupation", "Engineer", "high", "user_stated"
        )
        await life_context_service.upsert_fact(db, user_id, "family", "relationship_status", "married", "high", "user_stated")

        assert await life_context_service.delete_fact(db, user_id, career_item.id) is True

        all_active = await life_context_service.get_active_context(db, user_id)
        assert "career" not in all_active
        assert "family" in all_active

        family_only = await life_context_service.get_active_context(db, user_id, ["family"])
        assert "career" not in family_only
        assert family_only["family"]["relationship_status"]["value"] == "married"


async def test_delete_fact_returns_false_for_wrong_user_or_missing_id(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        assert await life_context_service.delete_fact(db, user_id, 999999) is False
        assert await life_context_service.delete_fact(db, "not-a-real-user", 1) is False


async def test_upsert_decision_creates_then_updates_the_same_open_decision(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        first = await life_context_service.upsert_decision(db, user_id, "job_change_decision", "lack of growth")
        assert first is not None
        assert first.decision_type == "job_change"
        assert first.status == "exploring"

        second = await life_context_service.upsert_decision(db, user_id, "job_change_decision", "got an offer now")
        assert second.id == first.id  # same row, not a duplicate
        assert second.context == "got an offer now"

        open_decisions = await life_context_service.get_open_decisions(db, user_id)
        assert len(open_decisions) == 1


async def test_upsert_decision_returns_none_for_a_non_decision_category(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        assert await life_context_service.upsert_decision(db, user_id, "career", "some note") is None


async def test_upsert_decision_supports_relocation_the_same_generic_way(client):
    """Phase 3 — relocation_decision has no get_decision verdict engine
    behind it (see _DECISION_TYPE_BY_CATEGORY's comment in
    life_context_service.py), but Decision Memory tracking itself is
    generic off that same dict, so it works identically to the two
    get_decision-backed types with zero decision_type-specific code."""
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        decision = await life_context_service.upsert_decision(db, user_id, "relocation_decision", "job offer abroad")
        assert decision is not None
        assert decision.decision_type == "relocation"
        assert decision.status == "exploring"

        marked = await life_context_service.mark_decision(db, user_id, "relocation_decision", "decided", "moved")
        assert marked.id == decision.id
        assert marked.status == "decided"
        assert await life_context_service.get_open_decisions(db, user_id) == []


async def test_correct_fact_records_as_user_confirmed_high_confidence(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        item = await life_context_service.upsert_fact(db, user_id, "career", "employer", "TCS", "low", "inferred")
        corrected = await life_context_service.correct_fact(db, user_id, item.id, "Infosys")
        assert corrected.value == "Infosys"
        assert corrected.confidence == "high"
        assert corrected.source == "user_confirmed"

        history = await life_context_service.get_fact_history(db, user_id, "career", "employer")
        assert [h["value"] for h in history] == ["TCS", "Infosys"]


async def test_correct_fact_returns_none_for_missing_item(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        assert await life_context_service.correct_fact(db, user_id, 999999, "x") is None


async def test_mark_decision_sets_decided_at_and_moves_out_of_open_decisions(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.upsert_decision(db, user_id, "job_change_decision", "lack of growth")
        decision = await life_context_service.mark_decision(db, user_id, "job_change_decision", "decided", "accepted new job")
        assert decision.status == "decided"
        assert decision.final_choice == "accepted new job"
        assert decision.decided_at is not None

        assert await life_context_service.get_open_decisions(db, user_id) == []


async def test_mark_decision_returns_none_when_no_open_decision_of_that_type(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        assert await life_context_service.mark_decision(db, user_id, "job_change_decision", "decided", "x") is None


async def test_decisions_due_for_outcome_checkin_respects_the_delay_window(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.upsert_decision(db, user_id, "job_change_decision", "lack of growth")
        decision = await life_context_service.mark_decision(db, user_id, "job_change_decision", "decided", "took the job")

        # Freshly decided — not due yet.
        assert await life_context_service.get_decisions_due_for_outcome_checkin(db, user_id) == []

        # Backdate decided_at past the check-in window.
        decision.decided_at = datetime.now(timezone.utc) - timedelta(days=100)
        await db.commit()

        due = await life_context_service.get_decisions_due_for_outcome_checkin(db, user_id)
        assert len(due) == 1
        assert due[0].id == decision.id


async def test_recording_an_outcome_removes_it_from_the_due_list(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.upsert_decision(db, user_id, "job_change_decision", "lack of growth")
        decision = await life_context_service.mark_decision(db, user_id, "job_change_decision", "decided", "took the job")
        decision.decided_at = datetime.now(timezone.utc) - timedelta(days=100)
        await db.commit()

        await life_context_service.record_outcome(db, user_id, decision.id, "better than expected")

        assert await life_context_service.get_decisions_due_for_outcome_checkin(db, user_id) == []
        all_decisions = await life_context_service.get_all_decisions(db, user_id)
        assert all_decisions[0].outcome == "better than expected"
        assert all_decisions[0].outcome_captured_at is not None


async def test_add_event_and_get_timeline_sorted_oldest_first(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await life_context_service.add_event(db, user_id, "promotion", "Promoted to Senior Engineer", 2024)
        await life_context_service.add_event(db, user_id, "new_job", "Joined TCS", 2022, 6)

        timeline = await life_context_service.get_timeline(db, user_id)
        assert [e["year"] for e in timeline] == [2022, 2024]
        assert timeline[0]["description"] == "Joined TCS"
        assert timeline[0]["month"] == 6


async def test_add_event_falls_back_to_other_for_unknown_type_and_clamps_implausible_year(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        event = await life_context_service.add_event(db, user_id, "won_lottery", "Won the lottery", 1500)
        assert event.event_type == "other"
        assert event.year == datetime.now(timezone.utc).year


def test_effective_confidence_decays_one_step_per_120_days_unconfirmed():
    now = datetime.now(timezone.utc)
    assert life_context_service.effective_confidence("high", now - timedelta(days=10)) == "high"
    assert life_context_service.effective_confidence("high", now - timedelta(days=130)) == "medium"
    assert life_context_service.effective_confidence("high", now - timedelta(days=250)) == "low"
    assert life_context_service.effective_confidence("medium", now - timedelta(days=130)) == "low"
    # Already "low" has nowhere further to decay to.
    assert life_context_service.effective_confidence("low", now - timedelta(days=1000)) == "low"


def test_effective_confidence_with_no_last_confirmed_at_returns_confidence_unchanged():
    assert life_context_service.effective_confidence("high", None) == "high"


async def test_get_facts_due_for_reconfirmation_only_returns_decayed_material_domain_facts(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        # Stale career fact — material domain, decayed to "low" — due.
        stale = await life_context_service.upsert_fact(
            db, user_id, "career", "employer", "TCS", "high", "user_stated"
        )
        stale.last_confirmed_at = datetime.now(timezone.utc) - timedelta(days=250)
        # Fresh career fact — not due yet.
        await life_context_service.upsert_fact(
            db, user_id, "career", "occupation", "Engineer", "high", "user_stated"
        )
        # Stale, but in a non-material domain (preferences) — never nagged about.
        stale_preference = await life_context_service.upsert_fact(
            db, user_id, "preferences", "favorite_color", "blue", "high", "user_stated"
        )
        stale_preference.last_confirmed_at = datetime.now(timezone.utc) - timedelta(days=250)
        await db.commit()

        due = await life_context_service.get_facts_due_for_reconfirmation(db, user_id)
        assert [d.id for d in due] == [stale.id]


async def test_reconfirming_a_fact_refreshes_last_confirmed_at_and_removes_it_from_due_list(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        fact = await life_context_service.upsert_fact(
            db, user_id, "career", "employer", "TCS", "high", "user_stated"
        )
        fact.last_confirmed_at = datetime.now(timezone.utc) - timedelta(days=250)
        await db.commit()
        assert len(await life_context_service.get_facts_due_for_reconfirmation(db, user_id)) == 1

        await life_context_service.upsert_fact(db, user_id, "career", "employer", "TCS", "high", "user_confirmed")

        assert await life_context_service.get_facts_due_for_reconfirmation(db, user_id) == []
        history = await life_context_service.get_fact_history(db, user_id, "career", "employer")
        assert len(history) == 1  # same value — refreshed in place, not a new history row
