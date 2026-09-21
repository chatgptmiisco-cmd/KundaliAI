"""Coverage for the Google Places-backed birth-place search proxy (see
app.services.geocoding_service) — mocks the outbound Google call so this
suite never makes a real network request or spends API quota."""
from app.services import geocoding_service
from tests.test_api_e2e import _signup_and_set_birth_data


async def test_geocode_search_requires_auth(client):
    resp = await client.get("/api/v1/geocode/search", params={"q": "Aligarh"})
    assert resp.status_code == 401


async def test_geocode_search_returns_real_looking_results(client, monkeypatch):
    headers = await _signup_and_set_birth_data(client)

    async def _fake_search_places(query: str) -> list[dict]:
        assert query == "Aligarh"
        return [{
            "display_name": "Aligarh, Uttar Pradesh, India",
            "latitude": 27.8973944,
            "longitude": 78.0880129,
            "timezone_offset_hours": 5.5,
        }]

    monkeypatch.setattr(geocoding_service, "search_places", _fake_search_places)

    resp = await client.get("/api/v1/geocode/search", headers=headers, params={"q": "Aligarh"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == [{
        "display_name": "Aligarh, Uttar Pradesh, India",
        "latitude": 27.8973944,
        "longitude": 78.0880129,
        "timezone_offset_hours": 5.5,
    }]


async def test_geocode_search_returns_empty_list_when_google_key_not_configured(client, monkeypatch):
    headers = await _signup_and_set_birth_data(client)
    settings = geocoding_service.get_settings()
    monkeypatch.setattr(settings, "google_places_api_key", None)
    monkeypatch.setattr(geocoding_service, "get_settings", lambda: settings)

    resp = await client.get("/api/v1/geocode/search", headers=headers, params={"q": "Aligarh"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_estimate_timezone_offset_prefers_known_country_over_longitude():
    assert geocoding_service._estimate_timezone_offset_hours("in", 78.0) == 5.5
    assert geocoding_service._estimate_timezone_offset_hours("IN", 78.0) == 5.5  # case-insensitive
    assert geocoding_service._estimate_timezone_offset_hours(None, 45.0) == 3  # falls back to longitude/15
    assert geocoding_service._estimate_timezone_offset_hours("us", -74.0) == -5  # unlisted country -> longitude
