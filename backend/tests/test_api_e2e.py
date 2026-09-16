"""End-to-end API flow: signup -> birth data -> charts -> dasha -> horoscope
-> period analysis (with quota) -> subscription upgrade -> premium charts ->
account deletion. Runs against the template (non-LLM) interpreter since no
ANTHROPIC_API_KEY is set in the test environment — this validates the
plumbing, not LLM output quality."""
import asyncio
from datetime import date, datetime, timezone

import pytest

from app.astro.event_window_scanner import ScoredWindow

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


def _effective_score(w: dict, bonus: float, penalty: float) -> float:
    score = w["score"]
    if w["transit_corroborated"]:
        score += bonus * w["transit_corroboration_strength"]
    if w["transit_obstructed"]:
        score -= penalty * w["transit_obstruction_fraction"]
    return score * w["age_plausibility_multiplier"]


_EVIDENCE_RANK = {"house_lord_antardasha": 0, "karaka_antardasha": 1, "backdrop_only": 2}


def _ranking_key(w: dict, bonus: float, penalty: float, direction: str = "future") -> tuple:
    # Mirrors prediction_service._rerank_with_transit_bonus's actual sort
    # key: evidence level and age-plausibility both outrank effective score
    # (see _pool_priority) — a window can have a lower effective score and
    # still legitimately sort first if it has stronger evidence or a more
    # plausible age. For direction="future" (v17), the window's own start
    # date outranks effective score too — the earliest window within the
    # same evidence/plausibility bucket wins, not the highest-scoring one
    # (see _rerank_with_transit_bonus's docstring); direction="past" keeps
    # score ahead of start, unchanged.
    bucket = (_EVIDENCE_RANK[w["evidence_level"]], not w["literal_event_plausible"])
    if direction == "future":
        return (*bucket, w["start_date"], -_effective_score(w, bonus, penalty))
    return (*bucket, -_effective_score(w, bonus, penalty), w["start_date"])


async def test_marriage_timing_returns_ranked_windows(client):
    """Windows are ranked by evidence level, then real-world age
    plausibility, then dasha score PLUS the Ashtakavarga-scaled transit-
    corroboration bonus MINUS the transit-obstruction penalty (see
    prediction_service._rerank_with_transit_bonus) — a window with a real,
    strong transit confirmation can legitimately outrank one with a higher
    raw dasha score but no transit signal, so the raw `score` field alone
    isn't expected to be monotonically decreasing on its own."""
    from app.services.prediction_service import _TRANSIT_CORROBORATION_BONUS, _TRANSIT_OBSTRUCTION_PENALTY

    headers = await _signup_and_set_birth_data(client)
    resp = await client.get("/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for window in data["windows"]:
        assert window["score"] > 0
        assert window["reason"]
        assert 0.0 < window["transit_corroboration_strength"] <= 1.5
        assert 0.0 <= window["transit_obstruction_fraction"] <= 1.0
        assert 0.15 <= window["age_plausibility_multiplier"] <= 1.0
    ranking_keys = [
        _ranking_key(w, _TRANSIT_CORROBORATION_BONUS, _TRANSIT_OBSTRUCTION_PENALTY) for w in data["windows"]
    ]
    assert ranking_keys == sorted(ranking_keys)


async def test_marriage_timing_earliest_window_wins_within_the_same_evidence_tier(client):
    """Regression guard for a real case a user found live, revised twice as
    the ranking rules genuinely changed underneath it:

    - Originally, a Saturn Mahadasha / Mercury Antardasha window (2027,
      lower raw dasha score) beat a later, higher-raw-score Mercury/Mercury
      window purely because Saturn was ALSO transiting the relevant house —
      before folding transit corroboration into ranking at all, the later,
      uncorroborated window wrongly won on raw dasha score alone.
    - Once Ashtakavarga was added (see app.astro.ashtakavarga), that same
      Saturn transit turned out to have only 2-out-of-8 Ashtakavarga bindus
      at the sign it was actually transiting — a real "this specific
      transit is weak" fact — which flipped the winner to the later,
      higher-scoring 2043 window for a while.
    - v17 (see prediction_service._TIMING_ALGO_VERSION) changed this again:
      for direction="future", the EARLIEST window within the same
      (is_hard_implausible, evidence_rank) bucket now wins outright instead
      of score (see _rerank_with_transit_bonus) — found right after v16
      widened the search horizon and several "future" answers started
      jumping to a merely-higher-scoring far-future window instead of an
      already-strong near one. Both 2027 and 2043 here are
      house_lord_antardasha and literal_event_plausible, i.e. the same
      bucket, so 2027 (earlier) now correctly wins regardless of either
      window's transit strength — locking in the CURRENT correct answer
      for this exact chart, same as the two revisions before it."""
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "transitcheck@example.com", "password": "supersecret1", "name": "Transit Check", "preferred_language": "en"},
    )
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    await client.put(
        "/api/v1/user/profile/birth-data",
        headers=headers,
        json={
            "name": "Transit Check", "date_of_birth": "2000-01-01", "time_of_birth": "06:34",
            "time_uncertain": False, "place_of_birth": "Mathura, Uttar Pradesh, India",
            "latitude": 27.4924, "longitude": 77.6737, "timezone_offset_hours": 5.5,
        },
    )
    resp = await client.get("/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"})
    assert resp.status_code == 200, resp.text
    windows = resp.json()["windows"]
    top = windows[0]
    assert top["start_date"] == "2027-02-20"
    assert top["evidence_level"] == "house_lord_antardasha"
    assert top["literal_event_plausible"] is True

    # 2043 has a higher raw score but starts later, in the SAME evidence/
    # plausibility bucket as 2027 — it no longer wins for direction="future".
    second = windows[1]
    assert second["start_date"] == "2043-02-16"
    assert second["score"] > top["score"]
    assert second["evidence_level"] == "house_lord_antardasha"


async def test_marriage_timing_is_cached_on_repeat_call(client):
    headers = await _signup_and_set_birth_data(client)
    first = await client.get("/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"})
    assert first.json()["cached"] is False
    second = await client.get("/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"})
    assert second.json()["cached"] is True


async def test_significator_strength_is_reused_across_timing_endpoints(client, monkeypatch):
    """_significator_strength (builds the full Shadbala natal chart — the
    single most expensive computation in the Prediction Engine) is identical
    for every one of marriage-timing + 4 life-event types x 2 directions for
    the same birth profile. Regression guard for the SignificatorStrengthCache
    layer: without it, each of those independently-cached endpoints was
    rebuilding the same Shadbala chart from scratch on its own first call."""
    from app.services import prediction_service

    calls = []
    real = prediction_service._significator_strength

    def _counting_wrapper(d1, birth):
        calls.append(1)
        return real(d1, birth)

    monkeypatch.setattr(prediction_service, "_significator_strength", _counting_wrapper)

    headers = await _signup_and_set_birth_data(client)
    marriage = await client.get("/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"})
    assert marriage.status_code == 200, marriage.text
    assert len(calls) == 1

    career = await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers, params={"event_type": "career", "language": "en"}
    )
    assert career.status_code == 200, career.text
    # Same birth profile, same algo version — the cache row from the
    # marriage-timing call above is reused, not recomputed.
    assert len(calls) == 1

    wealth_past = await client.get(
        "/api/v1/prediction/life-event-timing",
        headers=headers, params={"event_type": "wealth", "language": "en", "direction": "past"},
    )
    assert wealth_past.status_code == 200, wealth_past.text
    assert len(calls) == 1


@pytest.mark.parametrize("event_type", ["career", "wealth", "children", "foreign_travel"])
async def test_life_event_timing_returns_ranked_windows(client, event_type):
    """Same ranking rule as marriage timing — see the comment on
    test_marriage_timing_returns_ranked_windows above."""
    from app.services.prediction_service import _TRANSIT_CORROBORATION_BONUS, _TRANSIT_OBSTRUCTION_PENALTY

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
        assert 0.0 < window["transit_corroboration_strength"] <= 1.5
        assert 0.0 <= window["transit_obstruction_fraction"] <= 1.0
        assert 0.15 <= window["age_plausibility_multiplier"] <= 1.0
    ranking_keys = [
        _ranking_key(w, _TRANSIT_CORROBORATION_BONUS, _TRANSIT_OBSTRUCTION_PENALTY) for w in data["windows"]
    ]
    assert ranking_keys == sorted(ranking_keys)


@pytest.mark.parametrize("event_type", ["career", "wealth", "children", "foreign_travel"])
async def test_life_event_timing_age_plausibility_multiplier_matches_the_windows_actual_age(client, event_type):
    """Regression guard for a real gap found by comparing this engine's
    output against an independent chart read across several real charts:
    the classical dasha math alone can rank a chart's own infancy as its
    #1 "career"/"children" window, since the very first Antardasha of any
    life is structurally the strongest possible dasha-relationship
    combination. This checks the fix is actually wired end-to-end: every
    returned window's age_plausibility_multiplier must match what
    app.astro.life_stage_plausibility computes for that window's real age
    at the fixture's birth date (1990-01-25), not just exist as a field."""
    from app.astro.life_stage_plausibility import age_plausibility_multiplier

    headers = await _signup_and_set_birth_data(client)
    for direction in ("future", "past"):
        resp = await client.get(
            "/api/v1/prediction/life-event-timing", headers=headers,
            params={"event_type": event_type, "language": "en", "direction": direction},
        )
        assert resp.status_code == 200, resp.text
        birth_date = date(1990, 1, 25)
        for window in resp.json()["windows"]:
            start = date.fromisoformat(window["start_date"])
            age_years = (start - birth_date).days / 365.2425
            expected = age_plausibility_multiplier(event_type, age_years)
            assert window["age_plausibility_multiplier"] == pytest.approx(expected, abs=0.02)


async def test_life_event_timing_literal_event_plausible_matches_the_windows_actual_age(client):
    """Regression guard for the age/event-plausibility HARD constraint (see
    prediction_service._select_candidate_pool/_rerank_with_transit_bonus and
    app.astro.life_stage_plausibility.is_hard_implausible_age): every
    returned window's `literal_event_plausible` field must match the real
    hard-implausibility check for that window's actual age, and the reason
    text must carry an honest reinterpretation note whenever it's False —
    not just silently return the field."""
    from app.astro.life_stage_plausibility import is_hard_implausible_age

    headers = await _signup_and_set_birth_data(client)
    resp = await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers,
        params={"event_type": "wealth", "language": "en", "direction": "future"},
    )
    assert resp.status_code == 200, resp.text
    birth_date = date(1990, 1, 25)
    for window in resp.json()["windows"]:
        start = date.fromisoformat(window["start_date"])
        age_years = (start - birth_date).days / 365.2425
        expected = not is_hard_implausible_age("wealth", age_years)
        assert window["literal_event_plausible"] == expected
        if not expected:
            assert "family finances or shared household resources" in window["reason"]


async def test_marriage_timing_evidence_level_field_matches_reason_text(client):
    """Regression guard for the minimum-evidence gate: every returned
    window's `evidence_level` field must be consistent with whether its
    reason text carries the honest "backdrop-only" note — not a field that
    exists but never actually reflects real window content."""
    headers = await _signup_and_set_birth_data(client)
    for direction in ("future", "past"):
        resp = await client.get(
            "/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en", "direction": direction}
        )
        assert resp.status_code == 200, resp.text
        for window in resp.json()["windows"]:
            has_note = "broader multi-year period" in window["reason"]
            assert window["evidence_level"] in ("house_lord_antardasha", "karaka_antardasha", "backdrop_only")
            assert (window["evidence_level"] == "backdrop_only") == has_note


_CONFIDENCE_FOR_EVIDENCE = {"house_lord_antardasha": "strong", "karaka_antardasha": "moderate", "backdrop_only": "low"}


async def test_life_event_timing_confidence_field_matches_evidence_level(client):
    """Regression guard for the new `confidence` field (algo v15): it must
    always be the exact 1:1 mapping from `evidence_level`, and a
    backdrop_only window's reason text must LEAD with its low-confidence
    caveat rather than only appending it after a confident-sounding
    paragraph."""
    headers = await _signup_and_set_birth_data(client)
    for event_type in ("career", "wealth", "children", "foreign_travel"):
        for direction in ("future", "past"):
            resp = await client.get(
                "/api/v1/prediction/life-event-timing", headers=headers,
                params={"event_type": event_type, "language": "en", "direction": direction},
            )
            assert resp.status_code == 200, resp.text
            for window in resp.json()["windows"]:
                assert window["confidence"] == _CONFIDENCE_FOR_EVIDENCE[window["evidence_level"]]
                if window["evidence_level"] == "backdrop_only":
                    assert window["reason"].startswith("No strong, directly-tied window was found")


async def test_life_state_endpoint_round_trips_and_appears_in_profile(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.put(
        "/api/v1/user/profile/life-state", headers=headers,
        json={
            "marital_status": "married", "marriage_date": "2024-11-15", "children_count": 1,
            "pregnancy_status": "none", "career_state": "employed", "business_state": "none",
        },
    )
    assert resp.status_code == 200, resp.text
    life_state = resp.json()["life_state"]
    assert life_state == {
        "marital_status": "married", "marriage_date": "2024-11-15", "children_count": 1,
        "pregnancy_status": "none", "expected_delivery": None, "career_state": "employed",
        "business_state": "none", "version": 1,
    }

    profile = await client.get("/api/v1/user/profile", headers=headers)
    assert profile.json()["life_state"] == life_state


async def test_marriage_timing_reframes_reason_when_already_married(client):
    """v18: a user's own LifeState (married) reframes a FUTURE marriage_timing
    answer as married-life/relationship development rather than implying a
    first marriage that already happened. PAST queries are unaffected —
    "strongest past commitment period" is still a sensible question
    regardless of current marital status."""
    headers = await _signup_and_set_birth_data(client)
    await client.put(
        "/api/v1/user/profile/life-state", headers=headers,
        json={"marital_status": "married", "marriage_date": "2024-11-15"},
    )
    future = await client.get(
        "/api/v1/prediction/marriage-timing", headers=headers,
        params={"language": "en", "direction": "future"},
    )
    assert future.status_code == 200, future.text
    assert future.json()["cached"] is False  # freshly recomputed for the new life state
    for window in future.json()["windows"]:
        assert "You're already married as of 2024-11-15" in window["reason"]

    past = await client.get(
        "/api/v1/prediction/marriage-timing", headers=headers,
        params={"language": "en", "direction": "past"},
    )
    assert past.status_code == 200, past.text
    for window in past.json()["windows"]:
        assert "already married" not in window["reason"]


async def test_life_event_timing_reframes_reason_when_already_has_children(client):
    headers = await _signup_and_set_birth_data(client)
    await client.put(
        "/api/v1/user/profile/life-state", headers=headers,
        json={"children_count": 2, "pregnancy_status": "none"},
    )
    resp = await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers,
        params={"event_type": "children", "language": "en", "direction": "future"},
    )
    assert resp.status_code == 200, resp.text
    for window in resp.json()["windows"]:
        assert "You already have children" in window["reason"]

    # A different event type is unaffected by the children-specific note.
    career = await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers,
        params={"event_type": "career", "language": "en", "direction": "future"},
    )
    for window in career.json()["windows"]:
        assert "You already have children" not in window["reason"]


async def test_life_event_timing_anchors_to_expected_delivery_when_expecting(client):
    """v18: an already-expecting user's FUTURE children query must not run
    a blind search proposing a brand-new future child — it anchors
    directly to whichever Antardasha already covers their own
    expected_delivery date."""
    headers = await _signup_and_set_birth_data(client)
    await client.put(
        "/api/v1/user/profile/life-state", headers=headers,
        json={"pregnancy_status": "expecting", "expected_delivery": "2026-12-20"},
    )
    resp = await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers,
        params={"event_type": "children", "language": "en", "direction": "future"},
    )
    assert resp.status_code == 200, resp.text
    windows = resp.json()["windows"]
    assert len(windows) == 1
    window = windows[0]
    assert window["start_date"] <= "2026-12-20" <= window["end_date"]
    assert "expected delivery (2026-12-20)" in window["reason"]
    assert window["peak_window"] is None

    # Career (a different event type) is unaffected by the pregnancy override.
    career = await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers,
        params={"event_type": "career", "language": "en", "direction": "future"},
    )
    assert len(career.json()["windows"]) > 1


async def test_setting_life_state_invalidates_marriage_timing_cache(client):
    headers = await _signup_and_set_birth_data(client)
    first = await client.get(
        "/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"}
    )
    assert first.json()["cached"] is False
    second = await client.get(
        "/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"}
    )
    assert second.json()["cached"] is True  # unchanged life state -> still cached

    await client.put(
        "/api/v1/user/profile/life-state", headers=headers, json={"marital_status": "married"}
    )
    third = await client.get(
        "/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"}
    )
    assert third.json()["cached"] is False  # life-state edit invalidated the cache row


async def test_decision_job_change_returns_a_verdict_with_current_period(client):
    headers = await _signup_and_set_birth_data(client)
    resp = await client.get(
        "/api/v1/prediction/decision", headers=headers, params={"decision_type": "job_change", "language": "en"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["decision_type"] == "job_change"
    assert data["verdict"] in ("favorable", "unfavorable", "wait_for_better_window", "neutral")
    assert data["reasoning"]
    if data["verdict"] == "favorable":
        assert data["current_period"] is not None
        assert data["better_window"] is None
    if data["verdict"] == "wait_for_better_window":
        assert data["better_window"] is not None


async def test_decision_business_start_is_gated_by_life_state(client):
    """v20 (Phase 3): business_start reuses business_partnership's 7th-house
    gate — without a stated business intent, it must not return a verdict
    indistinguishable from marriage_timing's own signal."""
    headers = await _signup_and_set_birth_data(client)
    blocked = await client.get(
        "/api/v1/prediction/decision", headers=headers, params={"decision_type": "business_start", "language": "en"}
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["note"] is not None
    assert blocked.json()["current_period"] is None

    await client.put("/api/v1/user/profile/life-state", headers=headers, json={"business_state": "considering"})
    unblocked = await client.get(
        "/api/v1/prediction/decision", headers=headers, params={"decision_type": "business_start", "language": "en"}
    )
    assert unblocked.status_code == 200, unblocked.text
    assert unblocked.json()["note"] is None


async def test_decision_never_lets_history_override_a_clear_verdict(client, monkeypatch):
    """Regression guard for the core guardrail of the history-nudge feature:
    even with two consistent (and opposite-direction) prior verdicts
    logged, a fresh clear (non-neutral) verdict must never be touched."""
    from app.services import prediction_service

    headers = await _signup_and_set_birth_data(client)

    # Force a clear "favorable" verdict regardless of the real chart, then
    # confirm two opposing "unfavorable" priors don't flip it.
    forced_window = ScoredWindow(
        start=datetime(2020, 1, 1, tzinfo=timezone.utc), end=datetime(2023, 1, 1, tzinfo=timezone.utc),
        mahadasha_lord="Sa", antardasha_lord="Sa", score=10.0, reason_keys=["career_promotion_house_lord_antardasha"],
    )
    monkeypatch.setattr(prediction_service, "_is_currently_dusthana_afflicted", lambda *a, **kw: False)
    monkeypatch.setattr(prediction_service, "_current_period_score", lambda *a, **kw: forced_window)

    from app.db.base import AsyncSessionLocal
    from app.db.models.prediction_query_log import PredictionQueryLog
    from app.db.models.user import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        user_id = (await session.execute(select(User.id))).scalar_one()
        session.add(PredictionQueryLog(
            user_id=user_id, intent="job_change_decision", direction=None, language="en",
            result_summary={"verdict": "unfavorable"},
        ))
        session.add(PredictionQueryLog(
            user_id=user_id, intent="job_change_decision", direction=None, language="en",
            result_summary={"verdict": "unfavorable"},
        ))
        await session.commit()

    resp = await client.get(
        "/api/v1/prediction/decision", headers=headers, params={"decision_type": "job_change", "language": "en"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["verdict"] == "favorable"
    assert resp.json()["history_nudge"] is None


async def test_decision_nudges_a_neutral_verdict_toward_two_consistent_priors(client, monkeypatch):
    """The positive case: a genuinely borderline ("neutral") fresh reading,
    with the user's last two checks on this exact question both reading
    "favorable" — the nudge should fire and the reasoning should name it."""
    from app.services import prediction_service

    headers = await _signup_and_set_birth_data(client)

    monkeypatch.setattr(prediction_service, "_is_currently_dusthana_afflicted", lambda *a, **kw: False)
    monkeypatch.setattr(prediction_service, "_current_period_score", lambda *a, **kw: None)
    monkeypatch.setattr(prediction_service, "find_event_windows", lambda *a, **kw: [])

    from app.db.base import AsyncSessionLocal
    from app.db.models.prediction_query_log import PredictionQueryLog
    from app.db.models.user import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        user_id = (await session.execute(select(User.id))).scalar_one()
        for _ in range(2):
            session.add(PredictionQueryLog(
                user_id=user_id, intent="job_change_decision", direction=None, language="en",
                result_summary={"verdict": "favorable"},
            ))
        await session.commit()

    resp = await client.get(
        "/api/v1/prediction/decision", headers=headers, params={"decision_type": "job_change", "language": "en"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["verdict"] == "neutral"
    assert data["history_nudge"] == "favorable"
    assert "favorable" in data["reasoning"]


async def test_prediction_query_log_accumulates_across_timing_and_decision_calls(client):
    from app.db.base import AsyncSessionLocal
    from app.db.models.prediction_query_log import PredictionQueryLog
    from sqlalchemy import select

    headers = await _signup_and_set_birth_data(client)
    await client.get("/api/v1/prediction/marriage-timing", headers=headers, params={"language": "en"})
    await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers,
        params={"event_type": "career", "language": "en"},
    )
    await client.get(
        "/api/v1/prediction/decision", headers=headers, params={"decision_type": "job_change", "language": "en"}
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PredictionQueryLog))
        rows = result.scalars().all()

    intents = sorted(row.intent for row in rows)
    assert intents == ["career", "job_change_decision", "marriage_timing"]
    for row in rows:
        assert row.result_summary  # never an empty/missing summary


async def test_life_event_timing_reinterprets_a_window_with_no_plausible_age_alternative(client):
    """A child (age 10 today) searching PAST "wealth" timing (birth-to-now,
    so every candidate window is younger than wealth's hard_floor of 13) has
    no plausible-age alternative anywhere in the search horizon — the engine
    must still return its best available window, but flagged as a
    reinterpreted signal rather than a literal personal-wealth prediction."""
    today = date.today()
    ten_years_ago = today.replace(year=today.year - 10)
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "child@example.com", "password": "supersecret1", "name": "Child User", "preferred_language": "en"},
    )
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    await client.put(
        "/api/v1/user/profile/birth-data",
        headers=headers,
        json={
            "name": "Child User", "date_of_birth": ten_years_ago.isoformat(), "time_of_birth": "06:30",
            "time_uncertain": False, "place_of_birth": "New Delhi, India",
            "latitude": 28.6, "longitude": 77.2, "timezone_offset_hours": 5.5,
        },
    )
    resp = await client.get(
        "/api/v1/prediction/life-event-timing", headers=headers,
        params={"event_type": "wealth", "language": "en", "direction": "past"},
    )
    assert resp.status_code == 200, resp.text
    windows = resp.json()["windows"]
    assert windows  # a 10-year dasha timeline still has SOME scoring window
    for window in windows:
        assert window["literal_event_plausible"] is False
        assert "family finances or shared household resources" in window["reason"]


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
    assert len(body_a["doshas"]) == 5
    assert {d["key"] for d in body_a["doshas"]} == {"manglik", "kaal_sarp", "sade_sati", "dhaiya", "kemadruma"}
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
