"""Verifies the ALL_FEATURES_FREE override: every subscription-gated endpoint
must actually unlock when it's on, and the rest of the test suite (which runs
with it forced off — see conftest.py) proves the underlying tier/quota logic
still works correctly for whenever paywalls come back.
"""
from app.core.config import Settings


def test_all_features_free_defaults_to_true():
    # This is the real production default — paywalls are off "for now". Checked
    # against the field default directly (not an instance) since the test
    # environment explicitly sets ALL_FEATURES_FREE=false (see conftest.py) so
    # the tier-gating tests below can still exercise the real logic.
    assert Settings.model_fields["all_features_free"].default is True


async def test_d9_requires_insight_tier_when_gating_is_on(client):
    from tests.test_api_e2e import _signup_and_set_birth_data

    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/chart/d9", headers=headers)
    assert resp.status_code == 403


async def test_d9_unlocked_for_free_tier_when_all_features_free(client, monkeypatch):
    from app.core.config import get_settings
    from tests.test_api_e2e import _signup_and_set_birth_data

    free_settings = Settings(all_features_free=True)
    monkeypatch.setattr("app.api.deps.get_settings", lambda: free_settings)

    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/chart/d9", headers=headers)
    assert resp.status_code == 200, resp.text


async def test_period_analysis_quota_bypassed_when_all_features_free(client, monkeypatch):
    from app.core.config import get_settings
    from tests.test_api_e2e import _signup_and_set_birth_data

    free_settings = Settings(all_features_free=True)
    monkeypatch.setattr("app.services.analysis_service.get_settings", lambda: free_settings)

    headers = await _signup_and_set_birth_data(client)
    for i in range(5):  # well past the normal free_monthly_period_analyses=3 limit
        resp = await client.post(
            "/api/v1/analysis/period", headers=headers,
            json={"start_date": f"2025-0{i+1}-01", "end_date": f"2025-0{i+1}-28", "language": "en", "mode": "simple"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["remaining_free_analyses_this_month"] is None
