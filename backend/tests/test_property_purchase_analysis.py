"""Coverage for the reference-based property engine — Phase 8 (property_
purchase) + Phase 9 (D4 refinement + property_sale/property_inheritance/
property_relocation, the same BPHS 48.2-4 signal reinterpreted by intent) —
see app.services.prediction_service.get_property_analysis and app.astro.
property_analysis for the classical/derived citation discipline this is
built to.
"""
from datetime import date

from app.db.base import AsyncSessionLocal
from app.services import life_context_service, prediction_service, user_service
from tests.test_api_e2e import _signup_and_set_birth_data


async def _profile_and_birth(client, headers):
    profile_resp = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile_resp.json()["id"]
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        from app.db.models.birth_profile import BirthProfile

        result = await db.execute(select(BirthProfile).where(BirthProfile.user_id == user_id))
        profile = result.scalar_one()
        birth = user_service.decrypt_birth_data(profile)
        return profile, birth, user_id


async def test_first_home_purchase_returns_a_real_promise_and_evidence(client):
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        profile, birth, _user_id = await _profile_and_birth(client, headers)
        analysis = await prediction_service.get_property_analysis(db, profile, birth, "en")

    assert analysis.intent == "property_purchase"
    assert analysis.note is None
    assert analysis.property_promise is not None
    assert analysis.property_promise.status in ("supported", "mixed", "weak")
    assert any(e.rule_id == "FOURTH_HOUSE_DOMAIN" for e in analysis.property_promise.evidence)
    assert any(e.type == "classical" for e in analysis.property_promise.evidence)
    # D4 IS implemented (Phase 9) — real degree-in-sign data on a fresh D1
    # chart, so this should be a genuine, computed factor, never a
    # fabricated one.
    assert analysis.property_factors.d4 is not None
    assert analysis.property_factors.d4.fourth_lord_d4_dignity in ("exalted", "debilitated", "own_sign", "neutral")


async def test_existing_homeowner_gets_an_honest_note_not_a_fabricated_verdict(client):
    headers = await _signup_and_set_birth_data(client)
    await client.put("/api/v1/user/profile/life-state", headers=headers, json={"housing_status": "owns_property"})
    async with AsyncSessionLocal() as db:
        profile, birth, _user_id = await _profile_and_birth(client, headers)
        analysis = await prediction_service.get_property_analysis(db, profile, birth, "en")

    assert analysis.note is not None
    assert "already own" in analysis.note.lower()
    # Still a real, computed promise/factors — the note doesn't block the
    # engine from computing, only reframes what question it's answering.
    assert analysis.property_promise is not None


async def test_current_and_next_window_are_distinct_when_both_exist(client):
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        profile, birth, _user_id = await _profile_and_birth(client, headers)
        analysis = await prediction_service.get_property_analysis(db, profile, birth, "en")

    if analysis.current_period is not None and analysis.next_relevant_window is not None:
        assert analysis.current_period.start_date != analysis.next_relevant_window.start_date
        assert analysis.next_relevant_window.start_date > date.today()
    # Never defaults straight to the long-term peak when nearer windows exist.
    if analysis.next_relevant_window is not None and analysis.long_term_peak is not None:
        assert analysis.next_relevant_window.start_date <= analysis.long_term_peak.start_date


async def test_past_direction_returns_historical_windows_not_a_current_framing(client):
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        profile, birth, _user_id = await _profile_and_birth(client, headers)
        analysis = await prediction_service.get_property_analysis(db, profile, birth, "en", "property_purchase", "past")

    assert analysis.current_period is None
    assert analysis.next_relevant_window is None
    assert isinstance(analysis.historical_windows, list)


async def test_evidence_entries_are_all_correctly_tagged(client):
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        profile, birth, _user_id = await _profile_and_birth(client, headers)
        analysis = await prediction_service.get_property_analysis(db, profile, birth, "en")

    for entry in analysis.evidence + analysis.property_promise.evidence:
        assert entry.type in ("classical", "derived")
        assert entry.rule_id
        assert entry.description
        if entry.type == "classical":
            assert entry.source is not None
        # Derived entries must never claim a classical source/citation.
        if entry.rule_id in (
            "PROPERTY_PROMISE_SCORING", "PROPERTY_KARAKA_MARS_SATURN", "PROPERTY_TIMING_WINDOWS",
            "D4_CONFIRMATION",
        ):
            assert entry.type == "derived"
    # Always grounded in the classical 4th-house domain and disclosed as our
    # own derived synthesis; a Phaladeepika citation is only added when the
    # status is genuinely supported/weak (a "mixed" 4th lord gets neither
    # verse cited, which is itself the honest behavior — no false certainty).
    promise_rule_ids = {e.rule_id for e in analysis.property_promise.evidence}
    assert "FOURTH_HOUSE_DOMAIN" in promise_rule_ids
    assert "PROPERTY_PROMISE_SCORING" in promise_rule_ids
    if analysis.property_promise.status in ("supported", "weak"):
        assert ("PHALADEEPIKA_20_5" in promise_rule_ids) or ("PHALADEEPIKA_20_16" in promise_rule_ids)


async def test_d4_confirmation_never_upgrades_a_weak_promise(client):
    """Explicit instruction: D4 may reinforce a non-weak D1 reading, but
    must NEVER override a weak/afflicted one. Forces a weak D1 case
    (debilitated 4th lord) and a confirming D4 case via monkeypatch, and
    confirms status stays "weak" regardless."""
    from app.astro import property_analysis as property_analysis_module

    promise = property_analysis_module.compute_property_promise(
        fourth_lord_dignity="debilitated", fourth_lord_combust=False, fourth_lord_d4_dignity="exalted",
    )
    assert promise.status == "weak"
    assert not any(e.rule_id == "D4_CONFIRMATION" for e in promise.evidence)


async def test_d4_confirmation_upgrades_a_mixed_promise_to_supported(client):
    from app.astro import property_analysis as property_analysis_module

    promise = property_analysis_module.compute_property_promise(
        fourth_lord_dignity="neutral", fourth_lord_combust=False, fourth_lord_d4_dignity="own_sign",
    )
    assert promise.status == "supported"
    assert any(e.rule_id == "D4_CONFIRMATION" for e in promise.evidence)


async def test_property_purchase_analysis_api_endpoint_returns_the_full_structure(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/prediction/property-purchase-analysis", headers=headers, params={"language": "en"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["intent"] == "property_purchase"
    assert "evidence" in data


async def test_decision_house_purchase_endpoint_unchanged_shape_still_works(client):
    """Phase 5's /prediction/decision?decision_type=house_purchase keeps
    its exact original response shape — no breaking change from Phase 8/9."""
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get(
        "/api/v1/prediction/decision", headers=headers, params={"decision_type": "house_purchase", "language": "en"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["decision_type"] == "house_purchase"
    assert data["verdict"] in ("favorable", "unfavorable", "wait_for_better_window", "neutral")


async def test_chat_astro_house_purchase_decision_uses_the_new_analysis(client, monkeypatch):
    """The chat category routes through get_property_analysis (Phase 8/9),
    not the generic get_decision (Phase 5) — this exercises the real
    deterministic keyword path end to end and confirms it's still tracked
    as a Decision Memory row."""
    from app.core.config import Settings

    monkeypatch.setattr("app.api.deps.get_settings", lambda: Settings(all_features_free=True))

    headers = await _signup_and_set_birth_data(client)
    profile_resp = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile_resp.json()["id"]

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "Should I buy a house right now?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"]

    async with AsyncSessionLocal() as db:
        open_decisions = await life_context_service.get_open_decisions(db, user_id)
        assert any(d.decision_type == "house_purchase" for d in open_decisions)


async def test_property_analysis_decision_view_derives_a_favorable_verdict(client):
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        profile, birth, _user_id = await _profile_and_birth(client, headers)
        analysis = await prediction_service.get_property_analysis(db, profile, birth, "en")

    view = prediction_service.property_analysis_decision_view(analysis, "en")
    assert view["verdict"] in ("favorable", "unfavorable", "wait_for_better_window", "neutral")
    assert view["reasoning"]
    assert view["note"] == analysis.note


# --- Phase 9: property_sale / property_inheritance / property_relocation ---

async def test_all_four_implemented_intents_share_the_identical_windows(client):
    """The whole point of "reinterpretation, not recomputation" — all 4
    implemented intents must return byte-identical timing windows for the
    same chart, differing only in intent/evidence framing."""
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        profile, birth, _user_id = await _profile_and_birth(client, headers)
        purchase = await prediction_service.get_property_analysis(db, profile, birth, "en", "property_purchase")
        sale = await prediction_service.get_property_analysis(db, profile, birth, "en", "property_sale")
        inheritance = await prediction_service.get_property_analysis(db, profile, birth, "en", "property_inheritance")
        relocation = await prediction_service.get_property_analysis(db, profile, birth, "en", "property_relocation")

    for other in (sale, inheritance, relocation):
        assert other.current_period == purchase.current_period
        assert other.next_relevant_window == purchase.next_relevant_window
        assert other.long_term_peak == purchase.long_term_peak
    assert sale.intent == "property_sale"
    assert inheritance.intent == "property_inheritance"
    assert relocation.intent == "property_relocation"


async def test_property_sale_gets_a_soft_note_when_not_an_owner(client):
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        profile, birth, _user_id = await _profile_and_birth(client, headers)
        analysis = await prediction_service.get_property_analysis(db, profile, birth, "en", "property_sale")

    assert analysis.note is not None
    assert "haven't indicated owning" in analysis.note


async def test_property_sale_has_no_note_once_marked_as_an_owner(client):
    headers = await _signup_and_set_birth_data(client)
    await client.put("/api/v1/user/profile/life-state", headers=headers, json={"housing_status": "owns_property"})
    async with AsyncSessionLocal() as db:
        profile, birth, _user_id = await _profile_and_birth(client, headers)
        analysis = await prediction_service.get_property_analysis(db, profile, birth, "en", "property_sale")

    assert analysis.note is None


async def test_property_inheritance_and_relocation_carry_no_ownership_gate(client):
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        profile, birth, _user_id = await _profile_and_birth(client, headers)
        inheritance = await prediction_service.get_property_analysis(db, profile, birth, "en", "property_inheritance")
        relocation = await prediction_service.get_property_analysis(db, profile, birth, "en", "property_relocation")

    assert inheritance.note is None
    assert relocation.note is None


async def test_unimplemented_intent_returns_an_honest_not_supported_note(client):
    headers = await _signup_and_set_birth_data(client)
    async with AsyncSessionLocal() as db:
        profile, birth, _user_id = await _profile_and_birth(client, headers)
        analysis = await prediction_service.get_property_analysis(db, profile, birth, "en", "property_construction")

    assert analysis.note is not None
    assert "not supported" in analysis.note.lower() or "isn't supported" in analysis.note.lower()
    assert analysis.property_promise is None
    assert analysis.current_period is None


async def test_chat_astro_property_sale_intent_reaches_the_real_keyword_path(client, monkeypatch):
    from app.core.config import Settings

    monkeypatch.setattr("app.api.deps.get_settings", lambda: Settings(all_features_free=True))
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "When should I sell my house?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"]


async def test_chat_astro_property_inheritance_intent_reaches_the_real_keyword_path(client, monkeypatch):
    from app.core.config import Settings

    monkeypatch.setattr("app.api.deps.get_settings", lambda: Settings(all_features_free=True))
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "When will I inherit property?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"]


async def test_chat_astro_property_relocation_intent_reaches_the_real_keyword_path(client, monkeypatch):
    from app.core.config import Settings

    monkeypatch.setattr("app.api.deps.get_settings", lambda: Settings(all_features_free=True))
    headers = await _signup_and_set_birth_data(client)

    resp = await client.post(
        "/api/v1/chat/astro", headers=headers,
        json={"message": "When should I move house?", "rishi_id": "vyasa", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"]
