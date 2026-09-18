"""API-level coverage for the "My Life Twin" endpoints (product spec
§14-15/§10) — GET/PATCH/DELETE life-context and GET life-timeline."""
from app.db.base import AsyncSessionLocal
from app.services import life_context_service
from tests.test_api_e2e import _signup_and_set_birth_data


async def _real_user_id(client) -> str:
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    return profile.json()["id"]


async def test_get_life_twin_returns_facts_grouped_by_domain_and_decisions(client):
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    async with AsyncSessionLocal() as db:
        await life_context_service.upsert_fact(db, user_id, "career", "occupation", "Engineer", "high", "user_stated")
        await life_context_service.upsert_decision(db, user_id, "job_change_decision", "lack of growth")

    resp = await client.get("/api/v1/user/life-context", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["facts"]["career"][0]["value"] == "Engineer"
    assert body["decisions"][0]["decision_type"] == "job_change"
    assert body["decisions"][0]["status"] == "exploring"


async def test_patch_life_context_corrects_a_fact(client):
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    async with AsyncSessionLocal() as db:
        item = await life_context_service.upsert_fact(db, user_id, "career", "employer", "TCS", "high", "user_stated")

    resp = await client.patch(f"/api/v1/user/life-context/{item.id}", headers=headers, json={"value": "Infosys"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["value"] == "Infosys"
    assert resp.json()["source"] == "user_confirmed"


async def test_patch_life_context_404s_for_unknown_id(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.patch("/api/v1/user/life-context/999999", headers=headers, json={"value": "x"})
    assert resp.status_code == 404


async def test_delete_life_context_removes_a_fact_and_404s_second_time(client):
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    async with AsyncSessionLocal() as db:
        item = await life_context_service.upsert_fact(db, user_id, "family", "relationship_status", "married", "high", "user_stated")

    resp = await client.delete(f"/api/v1/user/life-context/{item.id}", headers=headers)
    assert resp.status_code == 204

    resp2 = await client.delete(f"/api/v1/user/life-context/{item.id}", headers=headers)
    assert resp2.status_code == 404

    twin = await client.get("/api/v1/user/life-context", headers=headers)
    assert "family" not in twin.json()["facts"]


async def test_get_life_timeline_returns_events_sorted_oldest_first(client):
    headers = await _signup_and_set_birth_data(client)
    profile = await client.get("/api/v1/user/profile", headers=headers)
    user_id = profile.json()["id"]

    async with AsyncSessionLocal() as db:
        await life_context_service.add_event(db, user_id, "promotion", "Promoted to Senior Engineer", 2024)
        await life_context_service.add_event(db, user_id, "new_job", "Joined TCS", 2022)

    resp = await client.get("/api/v1/user/life-timeline", headers=headers)
    assert resp.status_code == 200, resp.text
    years = [e["year"] for e in resp.json()]
    assert years == [2022, 2024]


async def test_onboarding_context_always_records_the_topic_as_main_concern(client):
    # AI is off in this test environment, so the richer per-answer
    # extraction won't run — but the topic itself must still be recorded,
    # since that alone is real signal regardless of AI availability.
    headers = await _signup_and_set_birth_data(client)
    resp = await client.post(
        "/api/v1/user/onboarding-context",
        headers=headers,
        json={"topic": "career", "qa_pairs": [{"question": "What do you do?", "answer": "Software engineer"}]},
    )
    assert resp.status_code == 204, resp.text

    twin = await client.get("/api/v1/user/life-context", headers=headers)
    assert twin.json()["facts"]["goals"][0]["value"] == "career"


async def test_life_twin_endpoints_require_auth(client):
    resp = await client.get("/api/v1/user/life-context")
    assert resp.status_code == 401
    resp = await client.get("/api/v1/user/life-timeline")
    assert resp.status_code == 401
