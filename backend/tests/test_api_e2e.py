"""End-to-end API flow: signup -> birth data -> charts -> dasha -> horoscope
-> period analysis (with quota) -> subscription upgrade -> premium charts ->
account deletion. Runs against the template (non-LLM) interpreter since no
ANTHROPIC_API_KEY is set in the test environment — this validates the
plumbing, not LLM output quality."""
import asyncio
from datetime import date

import pytest

from app.services.interpretation.templates import _LIFE_FRAMING_EN


async def _signup_and_set_birth_data(client) -> dict:
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "test@example.com", "password": "supersecret1", "name": "Test User", "preferred_language": "en"},
    )
    assert signup.status_code == 200, signup.text
    token = signup.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    birth = await client.put(
        "/api/v1/user/profile/birth-data",
        headers=headers,
        json={
            "name": "Test User", "date_of_birth": "1990-01-25", "time_of_birth": "06:30",
            "time_uncertain": False, "place_of_birth": "New Delhi, India",
            "latitude": 28.6, "longitude": 77.2, "timezone_offset_hours": 5.5,
        },
    )
    assert birth.status_code == 200, birth.text
    return headers


async def test_signup_requires_unique_email(client):
    await _signup_and_set_birth_data(client)
    dup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "test@example.com", "password": "supersecret1", "name": "Dup", "preferred_language": "en"},
    )
    assert dup.status_code == 409


async def test_login_wrong_password_rejected(client):
    await _signup_and_set_birth_data(client)
    resp = await client.post("/api/v1/auth/login", json={"email": "test@example.com", "password": "wrong"})
    assert resp.status_code == 401


async def test_profile_round_trip(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/user/profile", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["birth_data"]["name"] == "Test User"
    assert data["birth_data"]["place_of_birth"] == "New Delhi, India"
    assert data["subscription_tier"] == "free"


async def test_preferences_persist_server_side_and_survive_a_new_session(client):
    # Preferences used to live only in the client's local AsyncStorage — a
    # different device/browser signing into the same account saw an empty
    # list (and so no swipeable focus tabs at all), the same class of bug
    # birth data had before it was fixed to hydrate from the server.
    headers = await _signup_and_set_birth_data(client)

    profile = await client.get("/api/v1/user/profile", headers=headers)
    assert profile.json()["preferences"] == []

    resp = await client.put(
        "/api/v1/user/profile/preferences", headers=headers,
        json={"preferences": ["family", "career"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["preferences"] == ["family", "career"]

    # A fresh GET (simulating a different device/browser reading the same
    # account) sees the same preferences, not an empty list.
    profile_again = await client.get("/api/v1/user/profile", headers=headers)
    assert profile_again.json()["preferences"] == ["family", "career"]


async def test_preferences_reject_an_invalid_key(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.put(
        "/api/v1/user/profile/preferences", headers=headers,
        json={"preferences": ["family", "money"]},  # "money" was renamed away long ago
    )
    assert resp.status_code == 422


async def test_d1_chart_is_free_and_deterministic(client):
    headers = await _signup_and_set_birth_data(client)
    r1 = await client.get("/api/v1/chart/d1", headers=headers)
    assert r1.status_code == 200
    assert r1.json()["cached"] is False

    r2 = await client.get("/api/v1/chart/d1", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["cached"] is True
    assert r2.json()["lagna_sign_index"] == r1.json()["lagna_sign_index"]


async def test_d1_chart_includes_grah_spashta_precision_fields(client):
    headers = await _signup_and_set_birth_data(client)
    d1 = await client.get("/api/v1/chart/d1", headers=headers)
    assert d1.status_code == 200, d1.text
    body = d1.json()

    assert body["lagna_degree_in_sign"] is not None
    assert body["lagna_degree_display"].endswith("'")

    classical = {"Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa"}
    for planet in body["planets"]:
        assert 0 <= planet["degree_in_sign"] < 30
        assert planet["degree_display"].endswith("'")
        assert planet["nakshatra_name_en"]
        assert 1 <= planet["nakshatra_pada"] <= 4
        if planet["planet"] in classical:
            assert planet["dignity"] in {"exalted", "debilitated", "own_sign", "neutral"}
        else:  # Ra/Ke have no classical dignity
            assert planet["dignity"] is None

    d9 = await client.post(
        "/api/v1/subscription/checkout", headers=headers, json={"tier": "insight", "billing_cycle": "monthly"}
    )
    assert d9.status_code == 200
    d9_chart = await client.get("/api/v1/chart/d9", headers=headers)
    assert d9_chart.status_code == 200, d9_chart.text
    d9_body = d9_chart.json()
    # A divisional sign has no continuous degree of its own -> None on D9/D10.
    assert d9_body["lagna_degree_in_sign"] is None
    assert all(p["degree_in_sign"] is None for p in d9_body["planets"])
    # Nakshatra is a real-longitude fact, unaffected by which varga is shown.
    assert d9_body["planets"][0]["nakshatra_name_en"]


async def test_d1_chart_includes_house_breakdown_and_yoga_detection(client):
    headers = await _signup_and_set_birth_data(client)
    d1 = await client.get("/api/v1/chart/d1", headers=headers)
    assert d1.status_code == 200, d1.text
    body = d1.json()

    # Combustion: a real Sun-relative-longitude fact, computed for every
    # planet but always False for the Sun itself and for Rahu/Ketu (no
    # classical combustion orb applies to them).
    for p in body["planets"]:
        if p["planet"] in ("Su", "Ra", "Ke"):
            assert p["combust"] is False
        else:
            assert isinstance(p["combust"], bool)

    assert len(body["house_breakdown"]) == 12
    houses_with_planets = 0
    for house in body["house_breakdown"]:
        assert 1 <= house["house"] <= 12
        assert house["sign_name_en"]
        assert house["explanation_en"]
        assert house["explanation_hi"]
        if house["planets"]:
            houses_with_planets += 1
    assert houses_with_planets > 0  # a real chart always occupies some houses

    valid_yoga_keys = {
        "gajakesari", "mahapurusha_ma", "mahapurusha_me", "mahapurusha_ju", "mahapurusha_ve",
        "mahapurusha_sa", "raj_yoga", "manglik", "kaal_sarp", "kemadruma",
    }
    for yoga in body["yogas"]:
        assert yoga["key"] in valid_yoga_keys
        assert yoga["name_en"] and yoga["name_hi"]
        assert yoga["description_en"] and yoga["description_hi"]

    # D9/D10 also run yoga/dosha detection now (against that divisional
    # chart's own placements) — any findings must still be real, valid keys,
    # not necessarily the same ones D1 found.
    await client.post(
        "/api/v1/subscription/checkout", headers=headers, json={"tier": "insight", "billing_cycle": "monthly"}
    )
    d9 = await client.get("/api/v1/chart/d9", headers=headers)
    for yoga in d9.json()["yogas"]:
        assert yoga["key"] in valid_yoga_keys
        assert yoga["name_en"] and yoga["name_hi"]
    assert len(d9.json()["house_breakdown"]) == 12


async def test_d9_and_d10_require_insight_tier(client):
    headers = await _signup_and_set_birth_data(client)
    for path in ("/api/v1/chart/d9", "/api/v1/chart/d10"):
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 403

    checkout = await client.post(
        "/api/v1/subscription/checkout", headers=headers, json={"tier": "insight", "billing_cycle": "monthly"}
    )
    assert checkout.status_code == 200
    assert checkout.json()["simulated"] is True

    for path in ("/api/v1/chart/d9", "/api/v1/chart/d10"):
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200


async def test_dasha_timeline_and_current(client):
    headers = await _signup_and_set_birth_data(client)
    timeline = await client.get("/api/v1/dasha/timeline", headers=headers)
    assert timeline.status_code == 200
    mahadashas = timeline.json()["mahadashas"]
    assert len(mahadashas) == 9
    assert sum(1 for m in mahadashas if m["is_current"]) == 1

    current = await client.get("/api/v1/dasha/current", headers=headers)
    assert current.status_code == 200
    body = current.json()
    assert "mahadasha" in body and "antardasha" in body and "pratyantardasha" in body


async def test_daily_horoscope(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/horoscope/daily", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary_text"]
    assert body["cached"] is False

    resp2 = await client.get("/api/v1/horoscope/daily", headers=headers)
    assert resp2.json()["cached"] is True


async def test_period_analysis_free_quota_enforced(client):
    headers = await _signup_and_set_birth_data(client)

    # Free tier default quota is 3/month (see Settings.free_monthly_period_analyses)
    for i in range(3):
        resp = await client.post(
            "/api/v1/analysis/period", headers=headers,
            json={"start_date": f"2025-0{i+1}-01", "end_date": f"2025-0{i+1}-28", "language": "en", "mode": "simple"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["remaining_free_analyses_this_month"] == 2 - i

    over_limit = await client.post(
        "/api/v1/analysis/period", headers=headers,
        json={"start_date": "2025-04-01", "end_date": "2025-04-28", "language": "en", "mode": "simple"},
    )
    assert over_limit.status_code == 402


async def test_period_analysis_accepts_a_real_mahadasha_length_range(client):
    # PeriodAnalysisScreen's only caller of this endpoint analyzes a whole
    # Mahadasha at a time, not a short sub-period — a real Vimshottari
    # Mahadasha can run up to 20 years (Venus). This range (~19 years,
    # matching a real Saturn Mahadasha) previously 422'd against an old
    # "must not exceed one year" cap that had no computational basis — this
    # is the regression guard for that bug.
    headers = await _signup_and_set_birth_data(client)
    resp = await client.post(
        "/api/v1/analysis/period", headers=headers,
        json={"start_date": "2024-02-17", "end_date": "2043-02-16", "language": "en", "mode": "simple"},
    )
    assert resp.status_code == 200, resp.text
    assert 1 <= resp.json()["rating"] <= 10


async def test_period_analysis_uses_the_dasha_lord_actually_running_in_that_period_not_todays(client):
    """Regression guard: get_period_analysis used to call get_current_dasha()
    (always "today"), so analyzing a PAST Mahadasha silently described
    whatever lord happens to be running right now instead of that period's
    own lord. This locks in the fix using the birth fixture's very first
    Mahadasha (shortly after birth in 1990), which cannot possibly be the
    same lord as whatever is running decades later, "today"."""
    headers = await _signup_and_set_birth_data(client)

    timeline = await client.get("/api/v1/dasha/timeline", headers=headers)
    assert timeline.status_code == 200, timeline.text
    mahadashas = timeline.json()["mahadashas"]
    first_period = mahadashas[0]
    current_period = next(m for m in mahadashas if m["is_current"])
    assert first_period["lord"] != current_period["lord"]  # the fixture spans decades; this must hold

    resp = await client.post(
        "/api/v1/analysis/period", headers=headers,
        json={"start_date": first_period["start"][:10], "end_date": first_period["end"][:10], "language": "en", "mode": "simple"},
    )
    assert resp.status_code == 200, resp.text
    theme = resp.json()["theme"]
    # Pinned to the exact "{lord}'s broader Mahadasha" phrase the template
    # uses for the MAHADASHA slot specifically (not the antardasha slot,
    # which cycles through all 9 lords and could otherwise coincidentally
    # include the current lord's name too, making a bare substring check
    # unreliable).
    assert f"{first_period['lord_name_en']}'s broader Mahadasha" in theme
    assert f"{current_period['lord_name_en']}'s broader Mahadasha" not in theme


async def test_period_analysis_still_rejects_an_unreasonably_long_range(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.post(
        "/api/v1/analysis/period", headers=headers,
        json={"start_date": "2000-01-01", "end_date": "2100-01-01", "language": "en", "mode": "simple"},
    )
    assert resp.status_code == 422


async def test_repeat_period_analysis_is_cached_and_does_not_cost_quota(client):
    headers = await _signup_and_set_birth_data(client)
    body = {"start_date": "2025-01-01", "end_date": "2025-01-28", "language": "en", "mode": "simple"}

    first = await client.post("/api/v1/analysis/period", headers=headers, json=body)
    assert first.json()["remaining_free_analyses_this_month"] == 2

    second = await client.post("/api/v1/analysis/period", headers=headers, json=body)
    assert second.json()["cached"] is True
    assert second.json()["remaining_free_analyses_this_month"] == 2  # unchanged, no new usage


async def test_year_ahead_prediction_returns_a_real_computed_outlook(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/prediction/year-ahead", headers=headers, params={"language": "en"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert 1 <= data["overall_rating"] <= 10
    assert data["overall_theme"]
    assert data["varsheshwar"] in ("Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa")
    assert len(data["quarters"]) == 4
    for quarter in data["quarters"]:
        assert 1 <= quarter["rating"] <= 10
        assert quarter["theme"]


async def test_year_ahead_prediction_is_cached_on_repeat_call(client):
    headers = await _signup_and_set_birth_data(client)
    first = await client.get("/api/v1/prediction/year-ahead", headers=headers, params={"language": "en"})
    assert first.json()["cached"] is False
    second = await client.get("/api/v1/prediction/year-ahead", headers=headers, params={"language": "en"})
    assert second.json()["cached"] is True
    assert second.json()["quarters"] == first.json()["quarters"]


async def test_year_ahead_prediction_differs_between_two_real_charts(client):
    headers_a = await _signup_and_set_birth_data(client)
    a = await client.get("/api/v1/prediction/year-ahead", headers=headers_a, params={"language": "en"})

    signup_b = await client.post(
        "/api/v1/auth/signup",
        json={"email": "test2@example.com", "password": "supersecret1", "name": "Test User 2", "preferred_language": "en"},
    )
    headers_b = {"Authorization": f"Bearer {signup_b.json()['access_token']}"}
    await client.put(
        "/api/v1/user/profile/birth-data", headers=headers_b,
        json={
            "name": "Test User 2", "date_of_birth": "1985-06-10", "time_of_birth": "14:15",
            "time_uncertain": False, "place_of_birth": "Mumbai, India",
            "latitude": 19.07, "longitude": 72.87, "timezone_offset_hours": 5.5,
        },
    )
    b = await client.get("/api/v1/prediction/year-ahead", headers=headers_b, params={"language": "en"})

    assert a.json()["varsheshwar"] != b.json()["varsheshwar"] or a.json()["muntha_house"] != b.json()["muntha_house"]


async def test_multi_year_outlook_returns_requested_number_of_years(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/prediction/multi-year", headers=headers, params={"years": 2, "language": "en"})
    assert resp.status_code == 200, resp.text
    years = resp.json()["years"]
    assert len(years) == 2
    assert years[1]["year"] == years[0]["year"] + 1


async def test_multi_year_outlook_caps_at_the_maximum_allowed_years(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/prediction/multi-year", headers=headers, params={"years": 3, "language": "en"})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["years"]) == 3


async def test_marriage_timing_returns_ranked_windows(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for window in data["windows"]:
        assert window["score"] > 0
        assert window["reason"]
    scores = [w["score"] for w in data["windows"]]
    assert scores == sorted(scores, reverse=True)


async def test_marriage_timing_is_cached_on_repeat_call(client):
    headers = await _signup_and_set_birth_data(client)
    first = await client.get("/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"})
    assert first.json()["cached"] is False
    second = await client.get("/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"})
    assert second.json()["cached"] is True


@pytest.mark.parametrize("event_type", ["career", "wealth", "children", "foreign_travel"])
async def test_life_event_timing_returns_ranked_windows(client, event_type):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers, params={"event_type": event_type, "language": "en"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["event_type"] == event_type
    for window in data["windows"]:
        assert window["score"] > 0
        assert window["reason"]
    scores = [w["score"] for w in data["windows"]]
    assert scores == sorted(scores, reverse=True)


async def test_life_event_timing_is_cached_on_repeat_call(client):
    headers = await _signup_and_set_birth_data(client)
    first = await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers, params={"event_type": "career", "language": "en"}
    )
    assert first.json()["cached"] is False
    second = await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers, params={"event_type": "career", "language": "en"}
    )
    assert second.json()["cached"] is True


async def test_life_event_timing_rejects_an_invalid_event_type(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers, params={"event_type": "vehicle", "language": "en"}
    )
    assert resp.status_code == 422


async def test_marriage_timing_past_direction_returns_windows_within_the_persons_lifetime(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get(
        "/api/v1/prediction/marriage-timing", headers=headers, params={"direction": "past", "language": "en"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["direction"] == "past"
    today = date.today().isoformat()
    for window in data["windows"]:
        assert window["start_date"] >= "1990-01-25"  # the fixture's birth date
        assert window["end_date"] <= today
    # Past and future searches are cached separately, not the same row.
    future = await client.get(
        "/api/v1/prediction/marriage-timing", headers=headers, params={"direction": "future", "language": "en"}
    )
    assert future.json()["direction"] == "future"


async def test_life_event_timing_past_direction_returns_windows_within_the_persons_lifetime(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get(
        "/api/v1/prediction/life-event-timing",
        headers=headers, params={"event_type": "career", "direction": "past", "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["direction"] == "past"
    today = date.today().isoformat()
    for window in data["windows"]:
        assert window["start_date"] >= "1990-01-25"
        assert window["end_date"] <= today


async def test_life_theme_returns_the_real_historical_dasha_lord(client):
    headers = await _signup_and_set_birth_data(client)

    timeline = await client.get("/api/v1/dasha/timeline", headers=headers)
    assert timeline.status_code == 200, timeline.text
    first_period = timeline.json()["mahadashas"][0]

    resp = await client.get(
        "/api/v1/prediction/life-theme",
        headers=headers, params={"date": first_period["start"][:10], "language": "en"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mahadasha_lord"] == first_period["lord"]
    assert 1 <= data["rating"] <= 10
    assert data["theme"]
    # Honest tendency framing, never a fabricated specific claim.
    assert "you experienced" not in data["theme"].lower()


async def test_life_theme_is_cached_on_repeat_call(client):
    headers = await _signup_and_set_birth_data(client)
    first = await client.get(
        "/api/v1/prediction/life-theme", headers=headers, params={"date": "2000-06-15", "language": "en"}
    )
    assert first.status_code == 200, first.text
    assert first.json()["cached"] is False
    second = await client.get(
        "/api/v1/prediction/life-theme", headers=headers, params={"date": "2000-06-15", "language": "en"}
    )
    assert second.json()["cached"] is True


async def test_chat_astro_requires_strategy_tier(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.post("/api/v1/chat/astro", headers=headers, json={"message": "Hi", "language": "en"})
    assert resp.status_code == 403

    await client.post("/api/v1/subscription/checkout", headers=headers, json={"tier": "strategy", "billing_cycle": "monthly"})
    resp2 = await client.post("/api/v1/chat/astro", headers=headers, json={"message": "Hi", "language": "en"})
    assert resp2.status_code == 200
    assert resp2.json()["reply"]


async def test_voice_endpoints_require_insight_and_return_stub_shape(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.post(
        "/api/v1/voice/synthesize", headers=headers, json={"text": "hello", "language": "en"}
    )
    assert resp.status_code == 403

    await client.post("/api/v1/subscription/checkout", headers=headers, json={"tier": "insight", "billing_cycle": "monthly"})
    resp2 = await client.post(
        "/api/v1/voice/synthesize", headers=headers, json={"text": "hello", "language": "en"}
    )
    assert resp2.status_code == 200
    assert resp2.json()["stub"] is True
    assert resp2.json()["audio_url"] is None


async def test_delete_account_removes_profile(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.delete("/api/v1/user/account", headers=headers)
    assert resp.status_code == 204

    profile_resp = await client.get("/api/v1/user/profile", headers=headers)
    assert profile_resp.status_code == 401  # token now refers to a deleted user


async def test_concurrent_duplicate_requests_do_not_500(client):
    # Regression test for the race the frontend actually triggers: it fires
    # fetchSummary + fetchComplete (both hitting /kundali/complete) and
    # fetchManglik (which itself computes D1 + Manglik) all at once right
    # after onboarding. Two requests can both see "not cached yet" before
    # either commits — the second insert must not crash.
    headers = await _signup_and_set_birth_data(client)

    responses = await asyncio.gather(
        client.get("/api/v1/kundali/complete", headers=headers),
        client.get("/api/v1/kundali/complete", headers=headers),
        client.get("/api/v1/kundali/manglik", headers=headers),
    )
    for resp in responses:
        assert resp.status_code == 200, resp.text


async def test_manglik_status_is_consistent_with_d1_mars_house(client):
    headers = await _signup_and_set_birth_data(client)

    d1 = await client.get("/api/v1/chart/d1", headers=headers)
    mars = next(p for p in d1.json()["planets"] if p["planet"] == "Ma")

    manglik = await client.get("/api/v1/kundali/manglik", headers=headers)
    assert manglik.status_code == 200
    body = manglik.json()
    assert body["mars_house_from_lagna"] == mars["house"]
    assert body["is_manglik"] == (mars["house"] in (1, 2, 4, 7, 8, 12))
    assert body["summary"]

    cached = await client.get("/api/v1/kundali/manglik", headers=headers)
    assert cached.json()["cached"] is True


async def test_complete_kundali_has_all_six_sections_and_embeds_manglik(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/kundali/complete", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    section_ids = {s["id"] for s in body["sections"]}
    assert section_ids == {
        "personality_nature", "career_money", "relationships_marriage",
        "health_temperament", "strengths_challenges", "timing_overview",
    }
    assert len(body["basic_details"]) == 4
    assert body["brutal_truth"]
    assert body["manglik"]["is_manglik"] == body["summary"]["is_manglik"]

    cached = await client.get("/api/v1/kundali/complete", headers=headers)
    assert cached.json()["cached"] is True


async def test_complete_kundali_respects_language(client):
    headers = await _signup_and_set_birth_data(client)
    hi = await client.get("/api/v1/kundali/complete", headers=headers, params={"language": "hi"})
    assert hi.status_code == 200
    assert hi.json()["language"] == "hi"
    assert hi.json()["basic_details"][0]["label"] == "लग्न"


async def test_complete_kundali_brutal_truth_matches_actual_current_mahadasha_lord(client):
    # Regression test: kundali_service must thread the raw mahadasha lord key
    # (not just its localized display name) into the interpreter context —
    # otherwise the template silently defaults to the Moon's framing for
    # everyone, no matter whose chart it actually is.
    headers = await _signup_and_set_birth_data(client)

    current = await client.get("/api/v1/dasha/current", headers=headers)
    actual_lord_key = current.json()["mahadasha"]["lord"]

    complete = await client.get("/api/v1/kundali/complete", headers=headers)
    body = complete.json()

    expected = _LIFE_FRAMING_EN[actual_lord_key]
    assert body["brutal_truth"] == expected["brutal_truth"]
    assert body["summary"]["core_strength"] == expected["core_strength"]
    assert body["summary"]["core_challenge"] == expected["core_challenge"]


async def test_complete_kundali_core_strength_follows_real_chart_dignity_not_mahadasha_alone(client):
    # Regression test for the "two different users, same static text" bug:
    # this birth data's strongest planet (Moon, exalted) differs from its
    # current Mahadasha lord (Jupiter) — before the dignity-based fix,
    # core_strength was keyed to the Mahadasha lord alone, so it would have
    # rendered Jupiter's framing here instead of the chart's actual strongest
    # placement.
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "dignity@example.com", "password": "supersecret1", "name": "Dignity Test", "preferred_language": "en"},
    )
    token = signup.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    await client.put(
        "/api/v1/user/profile/birth-data", headers=headers,
        json={
            "name": "Dignity Test", "date_of_birth": "1985-07-14", "time_of_birth": "14:10",
            "time_uncertain": False, "place_of_birth": "New Delhi, India",
            "latitude": 28.6, "longitude": 77.2, "timezone_offset_hours": 5.5,
        },
    )

    current = await client.get("/api/v1/dasha/current", headers=headers)
    actual_lord_key = current.json()["mahadasha"]["lord"]
    assert actual_lord_key == "Ju"  # sanity-check the fixture hasn't drifted

    complete = await client.get("/api/v1/kundali/complete", headers=headers)
    body = complete.json()

    # The chart's actual strongest planet (Moon, exalted here) drives
    # core_strength, NOT the running Mahadasha lord (Jupiter).
    assert body["summary"]["core_strength"] == _LIFE_FRAMING_EN["Mo"]["core_strength"]
    assert body["summary"]["core_strength"] != _LIFE_FRAMING_EN["Ju"]["core_strength"]
    # brutal_truth stays tied to the Mahadasha lord (about the present chapter).
    assert body["brutal_truth"] == _LIFE_FRAMING_EN["Ju"]["brutal_truth"]


async def test_validation_questions_are_grounded_in_the_real_dasha_timeline(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/kundali/validation-questions", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["questions"]) >= 1
    for q in body["questions"]:
        assert q["period_start"] < q["period_end"]
        assert q["lord"] in {"Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Ra", "Ke"}
        assert 1 <= q["house"] <= 12
        assert q["statement"]
        # every question must be about a period that has actually finished
        assert q["period_end"] < date.today().isoformat()


async def test_guna_milan_returns_full_koota_breakdown(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.post(
        "/api/v1/kundali/guna-milan", headers=headers,
        json={
            "partner_name": "Partner", "partner_date_of_birth": "1992-06-10", "partner_time_of_birth": "14:15",
            "partner_place_of_birth": "Mumbai, India", "partner_latitude": 19.07, "partner_longitude": 72.87,
            "partner_timezone_offset_hours": 5.5, "language": "en",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["kootas"]) == 8
    assert {k["key"] for k in body["kootas"]} == {
        "varna", "vashya", "tara", "yoni", "graha_maitri", "gana", "bhakoot", "nadi",
    }
    assert sum(k["max_score"] for k in body["kootas"]) == 36.0
    assert 0.0 <= body["total_score"] <= 36.0
    assert body["verdict"] in {"excellent", "good", "average", "not_recommended"}
    assert body["your_moon_sign"]
    assert body["partner_moon_sign"]


async def test_guna_milan_validates_partner_birth_fields(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.post(
        "/api/v1/kundali/guna-milan", headers=headers,
        json={
            "partner_name": "Partner", "partner_date_of_birth": "1992-06-10", "partner_time_of_birth": "not-a-time",
            "partner_place_of_birth": "Mumbai, India", "partner_latitude": 19.07, "partner_longitude": 72.87,
            "partner_timezone_offset_hours": 5.5,
        },
    )
    assert resp.status_code == 422


async def test_daily_reading_returns_every_field_and_varies_by_chart(client):
    headers_a = await _signup_and_set_birth_data(client)

    signup_b = await client.post(
        "/api/v1/auth/signup",
        json={"email": "reading@example.com", "password": "supersecret1", "name": "Reading Test", "preferred_language": "en"},
    )
    token_b = signup_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}
    await client.put(
        "/api/v1/user/profile/birth-data", headers=headers_b,
        json={
            "name": "Reading Test", "date_of_birth": "1985-07-14", "time_of_birth": "14:10",
            "time_uncertain": False, "place_of_birth": "New Delhi, India",
            "latitude": 28.6, "longitude": 77.2, "timezone_offset_hours": 5.5,
        },
    )

    resp_a = await client.get("/api/v1/kundali/daily-reading", headers=headers_a)
    resp_b = await client.get("/api/v1/kundali/daily-reading", headers=headers_b)
    assert resp_a.status_code == 200, resp_a.text
    assert resp_b.status_code == 200, resp_b.text
    body_a, body_b = resp_a.json(), resp_b.json()

    required_fields = [
        "rating", "rating_reason", "dominant_theme", "energy_mode", "key_risk", "key_opportunity",
        "brutal_truth", "mahadasha_label", "period_rating", "period_type", "dominant_life_area",
        "core_strength", "core_weakness", "stress_pattern", "decision_style", "moon_nakshatra",
        "moon_mood_tag", "transit_highlight", "before_you_leave_home", "life_growth_task",
        "tithi_tag", "tithi_name", "paksha", "lunar_month", "today_color", "doshas",
        "lucky_number", "today_guidance",
    ]
    for field in required_fields:
        assert body_a[field] not in (None, "", []), f"{field} was empty for chart A"
        assert body_b[field] not in (None, "", []), f"{field} was empty for chart B"

    assert 1 <= body_a["rating"] <= 10
    assert 1 <= body_a["period_rating"] <= 10
    assert len(body_a["doshas"]) == 4
    assert {d["key"] for d in body_a["doshas"]} == {"manglik", "kaal_sarp", "sade_sati", "kemadruma"}
    assert len(body_a["before_you_leave_home"]) == 5
    # "festival" is nullable (None on an ordinary day) so it's checked for
    # presence/type here rather than in the strict non-empty loop above.
    assert "festival" in body_a
    assert body_a["festival"] is None or isinstance(body_a["festival"], str)
    # "jupiter_transiting_moon_sign" is a real boolean that can legitimately
    # be False, so it's also checked for presence/type rather than truthiness.
    assert isinstance(body_a["jupiter_transiting_moon_sign"], bool)

    # Two different birth charts must not collapse to the same natal facts —
    # the same regression guard as the earlier "static content" fixes.
    assert body_a["core_strength"] != body_b["core_strength"] or body_a["core_weakness"] != body_b["core_weakness"]
    assert body_a["moon_nakshatra"] != body_b["moon_nakshatra"]

    # Second call hits the cache.
    resp_a_again = await client.get("/api/v1/kundali/daily-reading", headers=headers_a)
    assert resp_a_again.json()["cached"] is True


async def test_focus_readings_covers_all_five_areas_with_real_house_facts(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/kundali/focus-readings", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["readings"]) == 5
    by_area = {r["area"]: r for r in body["readings"]}
    assert set(by_area) == {"family", "health", "career", "marriage_relationships", "friends"}
    assert by_area["family"]["house"] == 4
    assert by_area["health"]["house"] == 6
    assert by_area["career"]["house"] == 10
    assert by_area["marriage_relationships"]["house"] == 7
    assert by_area["friends"]["house"] == 11

    for reading in body["readings"]:
        assert reading["house_lord"] in {"Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Ra", "Ke"}
        assert 1 <= reading["house_lord_house"] <= 12
        assert reading["dignity"] in {"exalted", "debilitated", "own_sign", "neutral"}
        assert 1 <= reading["rating"] <= 10
        assert reading["summary"]
        assert reading["meaning"]
        assert reading["avoid_today"]
        assert reading["focus_today"]

    # Second call hits the cache.
    resp_again = await client.get("/api/v1/kundali/focus-readings", headers=headers)
    assert resp_again.json()["cached"] is True


async def test_otp_flow(client):
    request_resp = await client.post("/api/v1/auth/otp/request", json={"phone": "+919999999999"})
    assert request_resp.status_code == 200
    code = request_resp.json()["dev_code"]
    assert code and len(code) == 6

    wrong = await client.post("/api/v1/auth/otp/verify", json={"phone": "+919999999999", "code": "000000"})
    assert wrong.status_code == 401

    right = await client.post("/api/v1/auth/otp/verify", json={"phone": "+919999999999", "code": code})
    assert right.status_code == 200
    assert right.json()["access_token"]
