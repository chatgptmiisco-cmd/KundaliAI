"""Direct coverage for app.services.dynamic_question_service — durable
question+answer memory (DynamicQuestionLog) and anonymized cross-user
learning (QuestionPatternStats). Uses the real test DB with a real signed-up
user for the FK, same convention as test_life_context_service.py."""
from app.db.base import AsyncSessionLocal
from app.services import dynamic_question_service
from tests.test_api_e2e import _signup_and_set_birth_data


async def _real_user_id(client) -> str:
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    assert profile.status_code == 200, profile.text
    return profile.json()["id"]


async def test_log_question_then_record_answer_round_trips(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        entry = await dynamic_question_service.log_question(
            db, user_id, "vyasa", "business_category_suitability", "business_category_suitability",
            "How many hours a week could you realistically put into this?", "business", "weekly_hours",
            is_novel_concept=True, source="gpt_generated",
        )
        assert entry.status == "current"
        assert entry.answer_text is None

        answered = await dynamic_question_service.record_answer(db, entry.id, "about 10 hours", "10 hours/week", "high")
        assert answered.answer_text == "about 10 hours"
        assert answered.normalized_value == "10 hours/week"
        assert answered.answered_at is not None

        recent = await dynamic_question_service.get_recent_for_user(db, user_id)
        assert recent[0]["target_key"] == "weekly_hours"
        assert recent[0]["answer_text"] == "about 10 hours"


async def test_record_answer_for_unknown_question_id_is_a_safe_no_op(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        result = await dynamic_question_service.record_answer(db, 999999, "whatever", None, None)
        assert result is None


async def test_a_new_question_for_the_same_domain_key_marks_the_old_one_historical(client):
    """Mirrors LifeContextItem's own active/superseded convention — a later
    re-ask of the exact same concept must never leave two "current" rows
    contradicting each other."""
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        first = await dynamic_question_service.log_question(
            db, user_id, "vyasa", "business", None, "What would you sell?", "business", "goal",
            is_novel_concept=False, source="deterministic_fallback",
        )
        second = await dynamic_question_service.log_question(
            db, user_id, "vyasa", "business", None, "What would you sell, specifically?", "business", "goal",
            is_novel_concept=False, source="deterministic_fallback",
        )
        recent = await dynamic_question_service.get_recent_for_user(db, user_id, limit=10)
        by_id = {r["question_text"]: r["status"] for r in recent}
        assert by_id["What would you sell?"] == "historical"
        assert by_id["What would you sell, specifically?"] == "current"


async def test_question_pattern_stats_never_stores_user_id_or_raw_text(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await dynamic_question_service.log_question(
            db, user_id, "vyasa", "business_category_suitability", None, "What type of business?",
            "business", "business_type", is_novel_concept=False, source="gpt_generated",
        )
        from sqlalchemy import select
        from app.db.models.question_pattern_stats import QuestionPatternStats
        row = (await db.execute(select(QuestionPatternStats).where(
            QuestionPatternStats.category == "business_category_suitability",
            QuestionPatternStats.target_domain == "business",
            QuestionPatternStats.target_key == "business_type",
        ))).scalar_one()
        assert row.times_asked == 1
        assert not hasattr(row, "user_id")
        assert not hasattr(row, "question_text")
        assert not hasattr(row, "answer_text")


async def test_record_usefulness_only_increments_counters_that_actually_happened(client):
    user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await dynamic_question_service.log_question(
            db, user_id, "vyasa", "business", None, "How would you fund it?", "business", "funding",
            is_novel_concept=False, source="deterministic_fallback",
        )
        await dynamic_question_service.record_usefulness(
            db, "business", "business", "funding", answer_usable=True, answer_ready_after=True,
        )
        from sqlalchemy import select
        from app.db.models.question_pattern_stats import QuestionPatternStats
        row = (await db.execute(select(QuestionPatternStats).where(
            QuestionPatternStats.category == "business",
            QuestionPatternStats.target_domain == "business",
            QuestionPatternStats.target_key == "funding",
        ))).scalar_one()
        assert row.times_answer_usable == 1
        assert row.times_answer_ready_after == 1
        assert row.times_resolved_missing_information == 0
