"""Coverage for Phase 1's core bridge: a life fact stated in conversation
must update the SAME `LifeState` row `prediction_service` already reads to
redirect marriage/children/business predictions (see app.services.
user_service.apply_life_state_updates and app.api.v1.chat's life_state_update
handling) — not just the free-form LifeContextItem facts used for prose.

Also covers the "vague past-event" fallback (app.api.v1.chat.
_recent_past_candidate) and the richer per-window context fields now reaching
the chat interpreter's prompt (app.services.interpretation.openai_interpreter.
_chat_facts).
"""
from datetime import date

import pytest

from app.api.v1 import chat as chat_module
from app.core.config import Settings
from app.db.base import AsyncSessionLocal
from app.schemas.prediction import LifeEventTimingResponse, LifeEventWindow, MarriageTimingResponse, MarriageWindow
from app.services import user_service
from app.services.chat_understanding import ChatUnderstanding, LifeStateUpdate
from app.services.interpretation.openai_interpreter import _chat_facts
from tests.test_api_e2e import _signup_and_set_birth_data


def _unlock_strategy_tier(monkeypatch):
    monkeypatch.setattr("app.api.deps.get_settings", lambda: Settings(all_features_free=True))


async def _real_user_id(client) -> str:
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    return headers, profile.json()["id"]


# --- apply_life_state_updates (service-level partial merge) ----------------


async def test_apply_life_state_updates_creates_a_row_from_nothing(client):
    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        result = await user_service.apply_life_state_updates(db, user_id, marital_status="married")
        assert result.marital_status == "married"
        assert result.version == 1


async def test_apply_life_state_updates_merges_without_wiping_unrelated_fields(client):
    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        await user_service.apply_life_state_updates(db, user_id, marital_status="married")
        result = await user_service.apply_life_state_updates(db, user_id, career_state="employed")
        assert result.marital_status == "married"  # NOT wiped by the second, unrelated update
        assert result.career_state == "employed"
        assert result.version == 2


async def test_apply_life_state_updates_drops_an_invalid_value_instead_of_crashing(client):
    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        # "engaged_to_be_married" isn't one of the real allowed values —
        # must be dropped, not raise, and must not wipe out other fields.
        await user_service.apply_life_state_updates(db, user_id, marital_status="married")
        result = await user_service.apply_life_state_updates(
            db, user_id, marital_status="engaged_to_be_married", career_state="employed"
        )
        assert result.marital_status == "married"  # unchanged — bad value dropped
        assert result.career_state == "employed"  # valid sibling field still applied


async def test_apply_life_state_updates_parses_a_real_date_string(client):
    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        result = await user_service.apply_life_state_updates(
            db, user_id, marital_status="married", marriage_date="2024-11-15"
        )
        decrypted = user_service.decrypt_life_state(result)
        assert decrypted.marriage_date == date(2024, 11, 15)


async def test_apply_life_state_updates_with_no_valid_fields_is_a_no_op(client):
    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        result = await user_service.apply_life_state_updates(db, user_id, marital_status="not_a_real_status")
        assert result is None  # nothing valid to apply, no row was ever created


# --- The chat-driven bridge, end to end -------------------------------------


async def test_chat_life_state_update_reaches_the_same_row_the_engine_reads(client, monkeypatch):
    """A crafted ChatUnderstanding (classify_message itself needs a real
    OpenAI call the test environment deliberately disables — see
    conftest.py) stands in for what the LLM would produce when a user
    states "I got married." What's under test is chat.py's OWN wiring:
    does it actually call apply_life_state_updates, and does that reach the
    exact row prediction_service's already-tested redirect logic reads."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    async def _fake_classify_message(*args, **kwargs):
        return ChatUnderstanding(
            categories=[],
            life_state_update=LifeStateUpdate(marital_status="married", marriage_date="2024-11-15"),
        )

    monkeypatch.setattr(chat_module, "classify_message", _fake_classify_message)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": "I got married in November 2024", "language": "en"}
    )
    assert resp.status_code == 200, resp.text

    profile = await client.get("/api/v1/user/profile", headers=headers)
    life_state = profile.json()["life_state"]
    assert life_state["marital_status"] == "married"
    assert life_state["marriage_date"] == "2024-11-15"

    # Same assertion test_marriage_timing_reframes_reason_when_already_married
    # already makes for the settings-form path — proving the chat-driven
    # write landed in the identical row, not a parallel one.
    future = await client.get(
        "/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en", "direction": "future"}
    )
    assert future.status_code == 200, future.text
    for window in future.json()["windows"]:
        assert "You're already married as of 2024-11-15" in window["reason"]


async def test_chat_life_state_update_ignores_a_field_the_message_never_stated(client, monkeypatch):
    """LifeStateUpdate's unset fields are None, not "clear this" — chat.py
    must only forward the fields that were actually set."""
    _unlock_strategy_tier(monkeypatch)
    headers = await _signup_and_set_birth_data(client)

    async def _fake_classify_message(*args, **kwargs):
        return ChatUnderstanding(categories=[], life_state_update=LifeStateUpdate(career_state="employed"))

    monkeypatch.setattr(chat_module, "classify_message", _fake_classify_message)
    resp = await client.post(
        "/api/v1/chat/astro", headers=headers, json={"message": "I'm currently employed as an engineer", "language": "en"}
    )
    assert resp.status_code == 200, resp.text

    profile = await client.get("/api/v1/user/profile", headers=headers)
    life_state = profile.json()["life_state"]
    assert life_state["career_state"] == "employed"
    assert life_state["marital_status"] is None  # never mentioned — must stay unset, not defaulted


# --- Vague past-event fallback ----------------------------------------------


def _fake_marriage_window(start: date, end: date, confidence: str, score: float) -> MarriageWindow:
    return MarriageWindow(
        start_date=start, end_date=end, mahadasha_lord="Ju", mahadasha_lord_name="Jupiter",
        antardasha_lord="Ve", antardasha_lord_name="Venus", score=score,
        reason="test reason", transit_corroborated=False, transit_corroboration_strength=1.0,
        transit_obstructed=False, transit_obstruction_fraction=0.0, age_plausibility_multiplier=1.0,
        literal_event_plausible=True, evidence_level="karaka_antardasha", confidence=confidence,
        stage="serious_commitment", d9_confirmed=False,
    )


def _fake_life_event_window(start: date, end: date, confidence: str, score: float) -> LifeEventWindow:
    return LifeEventWindow(
        start_date=start, end_date=end, mahadasha_lord="Sa", mahadasha_lord_name="Saturn",
        antardasha_lord="Su", antardasha_lord_name="Sun", score=score,
        reason="test reason", transit_corroborated=False, transit_corroboration_strength=1.0,
        transit_obstructed=False, transit_obstruction_fraction=0.0, age_plausibility_multiplier=1.0,
        literal_event_plausible=True, evidence_level="karaka_antardasha", confidence=confidence,
    )


async def test_recent_past_candidate_prefers_a_window_inside_the_recent_horizon(client, monkeypatch):
    current_year = date.today().year
    old_window = _fake_marriage_window(date(1999, 1, 1), date(1999, 6, 1), "strong", 10.0)
    recent_window = _fake_life_event_window(
        date(current_year - 3, 1, 1), date(current_year - 3, 6, 1), "moderate", 5.0
    )

    async def _fake_marriage_timing(*args, **kwargs):
        return MarriageTimingResponse(language="en", direction="past", windows=[old_window], manglik_note=None, cached=False)

    async def _fake_life_event_timing(*args, **kwargs):
        return LifeEventTimingResponse(
            event_type="career", language="en", direction="past", windows=[recent_window], cached=False
        )

    monkeypatch.setattr(chat_module.prediction_service, "get_marriage_timing", _fake_marriage_timing)
    monkeypatch.setattr(chat_module.prediction_service, "get_life_event_timing", _fake_life_event_timing)

    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        profile = await user_service.get_birth_profile(db, user_id)
        birth = user_service.decrypt_birth_data(profile)
        candidate = await chat_module._recent_past_candidate(db, profile, birth, "en")

    assert candidate is not None
    assert candidate["domains"] == ["career"]  # the recent one, despite the marriage window scoring higher
    assert candidate["start_date"] == date(current_year - 3, 1, 1).isoformat()


async def test_recent_past_candidate_returns_none_when_nothing_is_recent(client, monkeypatch):
    old_window = _fake_marriage_window(date(1999, 1, 1), date(1999, 6, 1), "strong", 10.0)

    async def _fake_marriage_timing(*args, **kwargs):
        return MarriageTimingResponse(language="en", direction="past", windows=[old_window], manglik_note=None, cached=False)

    async def _fake_life_event_timing(*args, **kwargs):
        return LifeEventTimingResponse(event_type="career", language="en", direction="past", windows=[], cached=False)

    monkeypatch.setattr(chat_module.prediction_service, "get_marriage_timing", _fake_marriage_timing)
    monkeypatch.setattr(chat_module.prediction_service, "get_life_event_timing", _fake_life_event_timing)

    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        profile = await user_service.get_birth_profile(db, user_id)
        birth = user_service.decrypt_birth_data(profile)
        candidate = await chat_module._recent_past_candidate(db, profile, birth, "en")

    assert candidate is None  # never surfaces a childhood-era window just because it's the only one


async def test_recent_past_candidate_combines_two_domains_when_windows_overlap(client, monkeypatch):
    """Product spec §20 — Cross-Domain Events: overlapping career and
    relationship windows in the recent past become ONE combined candidate
    instead of the selection logic silently discarding the weaker domain."""
    current_year = date.today().year
    overlapping_marriage = _fake_marriage_window(
        date(current_year - 3, 3, 1), date(current_year - 3, 9, 1), "strong", 10.0
    )
    overlapping_career = _fake_life_event_window(
        date(current_year - 3, 1, 1), date(current_year - 3, 6, 1), "moderate", 5.0
    )

    async def _fake_marriage_timing(*args, **kwargs):
        return MarriageTimingResponse(
            language="en", direction="past", windows=[overlapping_marriage], manglik_note=None, cached=False
        )

    async def _fake_life_event_timing(*args, **kwargs):
        return LifeEventTimingResponse(
            event_type="career", language="en", direction="past", windows=[overlapping_career], cached=False
        )

    monkeypatch.setattr(chat_module.prediction_service, "get_marriage_timing", _fake_marriage_timing)
    monkeypatch.setattr(chat_module.prediction_service, "get_life_event_timing", _fake_life_event_timing)

    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        profile = await user_service.get_birth_profile(db, user_id)
        birth = user_service.decrypt_birth_data(profile)
        candidate = await chat_module._recent_past_candidate(db, profile, birth, "en")

    assert candidate is not None
    assert set(candidate["domains"]) == {"career", "relationships"}
    # The intersection of the two ranges: max(starts) to min(ends).
    assert candidate["start_date"] == date(current_year - 3, 3, 1).isoformat()
    assert candidate["end_date"] == date(current_year - 3, 6, 1).isoformat()
    assert candidate["confidence"] == "moderate"  # the weaker of the two, not the stronger


async def test_recent_past_candidate_does_not_combine_non_overlapping_windows(client, monkeypatch):
    current_year = date.today().year
    early_marriage = _fake_marriage_window(
        date(current_year - 5, 1, 1), date(current_year - 5, 3, 1), "strong", 10.0
    )
    late_career = _fake_life_event_window(
        date(current_year - 2, 1, 1), date(current_year - 2, 6, 1), "moderate", 5.0
    )

    async def _fake_marriage_timing(*args, **kwargs):
        return MarriageTimingResponse(
            language="en", direction="past", windows=[early_marriage], manglik_note=None, cached=False
        )

    async def _fake_life_event_timing(*args, **kwargs):
        return LifeEventTimingResponse(
            event_type="career", language="en", direction="past", windows=[late_career], cached=False
        )

    monkeypatch.setattr(chat_module.prediction_service, "get_marriage_timing", _fake_marriage_timing)
    monkeypatch.setattr(chat_module.prediction_service, "get_life_event_timing", _fake_life_event_timing)

    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        profile = await user_service.get_birth_profile(db, user_id)
        birth = user_service.decrypt_birth_data(profile)
        candidate = await chat_module._recent_past_candidate(db, profile, birth, "en")

    assert candidate is not None
    assert len(candidate["domains"]) == 1  # today's single-best behavior, unchanged when nothing overlaps
    assert candidate["domains"] == ["relationships"]  # strong beats moderate


async def test_recent_past_candidate_widens_to_ten_years_when_nothing_is_within_five(client, monkeypatch):
    """Phase 10 (spec §17) — primarily search the last 5 years; only widen
    to 10 when nothing at all falls in that tighter window. A window at
    current_year-7 is outside the 5-year primary pass but inside the
    10-year fallback, and must still be found."""
    current_year = date.today().year
    seven_years_ago = _fake_life_event_window(
        date(current_year - 7, 1, 1), date(current_year - 7, 6, 1), "moderate", 5.0
    )

    async def _fake_marriage_timing(*args, **kwargs):
        return MarriageTimingResponse(language="en", direction="past", windows=[], manglik_note=None, cached=False)

    async def _fake_life_event_timing(*args, **kwargs):
        return LifeEventTimingResponse(
            event_type="career", language="en", direction="past", windows=[seven_years_ago], cached=False
        )

    monkeypatch.setattr(chat_module.prediction_service, "get_marriage_timing", _fake_marriage_timing)
    monkeypatch.setattr(chat_module.prediction_service, "get_life_event_timing", _fake_life_event_timing)

    _, user_id = await _real_user_id(client)
    async with AsyncSessionLocal() as db:
        profile = await user_service.get_birth_profile(db, user_id)
        birth = user_service.decrypt_birth_data(profile)
        candidate = await chat_module._recent_past_candidate(db, profile, birth, "en")

    assert candidate is not None
    assert candidate["domains"] == ["career"]
    assert candidate["start_date"] == date(current_year - 7, 1, 1).isoformat()


# --- Enriched context fields reach the interpreter's prompt -----------------


def test_chat_facts_forwards_evidence_and_long_term_peak_for_a_timing_category():
    context = {
        "detected_categories": ["marriage_timing"],
        "marriage_timing_windows": [
            {
                "start_date": "2026-01-01", "end_date": "2026-06-01", "reason": "x",
                "antardasha_lord_name": "Venus", "transit_corroborated": True,
                "evidence_level": "house_lord_antardasha", "confidence": "strong",
                "literal_event_plausible": True,
                "peak_window": {"start_date": "2026-02-01", "end_date": "2026-03-01"},
            }
        ],
        "marriage_timing_long_term_peak": {
            "start_date": "2030-01-01", "end_date": "2030-06-01", "antardasha_lord_name": "Jupiter",
        },
    }
    in_domain, out_of_domain = _chat_facts(context, out_of_domain_categories=set())
    assert out_of_domain == {}
    window = in_domain["marriage_timing_windows"][0]
    assert window["evidence_level"] == "house_lord_antardasha"
    assert window["confidence"] == "strong"
    assert window["literal_event_plausible"] is True
    assert window["peak_window"] == {"start_date": "2026-02-01", "end_date": "2026-03-01"}
    assert in_domain["marriage_timing_long_term_peak"]["antardasha_lord_name"] == "Jupiter"


def test_chat_facts_forwards_past_event_candidate_for_life_theme():
    context = {
        "detected_categories": ["life_theme"],
        "past_event_candidate": {
            "domains": ["career"], "start_date": "2022-01-01", "end_date": "2022-06-01",
            "reason": "x", "confidence": "moderate",
        },
    }
    in_domain, _ = _chat_facts(context, out_of_domain_categories=set())
    assert in_domain["past_event_candidate"]["domains"] == ["career"]
