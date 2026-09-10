"""Layer 1 of the Charts redesign: GET /kundali/identity. Cross-checks the
reshaped identity payload against the same D1 chart fetched directly, so this
proves the reshaping logic (right meaning attached to the right sign, right
nakshatra symbol/meaning at the right index, a full Lagna+9-graha element/
modality breakdown) rather than re-deriving ephemeris values by hand."""
from app.astro.constants import (
    ELEMENT_NAMES_EN,
    MODALITY_NAMES_EN,
    NAKSHATRA_MEANING_EN,
    NAKSHATRA_NAMES_EN,
    NAKSHATRA_SYMBOL_EN,
    PLANET_NAMES_EN,
    SIGN_ELEMENT,
    SIGN_MODALITY,
)
from tests.test_api_e2e import _signup_and_set_birth_data


async def test_identity_matches_the_real_d1_chart(client):
    headers = await _signup_and_set_birth_data(client)

    d1 = await client.get("/api/v1/chart/d1", headers=headers)
    assert d1.status_code == 200, d1.text
    chart = d1.json()

    resp = await client.get("/api/v1/kundali/identity", headers=headers)
    assert resp.status_code == 200, resp.text
    identity = resp.json()

    # Big Three match the real chart, not a canned value.
    assert identity["lagna"]["sign_en"] == chart["lagna_sign_name_en"]
    assert identity["lagna"]["meaning_en"]
    moon = next(p for p in chart["planets"] if p["planet"] == "Mo")
    sun = next(p for p in chart["planets"] if p["planet"] == "Su")
    assert identity["moon_sign"]["sign_en"] == moon["sign_name_en"]
    assert identity["sun_sign"]["sign_en"] == sun["sign_name_en"]

    # Each Big Three point leads with a real per-chart consequence (where it
    # actually sits and how well-placed it is), not just the fixed glossary
    # definition — the house number named must match this real chart.
    assert str(moon["house"]) in identity["moon_sign"]["real_effect_en"]
    assert str(sun["house"]) in identity["sun_sign"]["real_effect_en"]
    assert identity["lagna"]["real_effect_en"] != identity["moon_sign"]["real_effect_en"]

    # Nakshatra is the Moon's real nakshatra, with a real lord/symbol/meaning
    # at the matching index — not an arbitrary/static one.
    assert identity["nakshatra"]["name_en"] == moon["nakshatra_name_en"]
    assert identity["nakshatra"]["pada"] == moon["nakshatra_pada"]
    nak_index = NAKSHATRA_NAMES_EN.index(moon["nakshatra_name_en"])
    assert identity["nakshatra"]["symbol_en"] == NAKSHATRA_SYMBOL_EN[nak_index]
    assert identity["nakshatra"]["meaning_en"] == NAKSHATRA_MEANING_EN[nak_index]
    assert identity["nakshatra"]["lord_en"] in PLANET_NAMES_EN.values()

    # Element/modality: Lagna + all 9 grahas, each matching SIGN_ELEMENT/
    # SIGN_MODALITY for the sign that point actually occupies in the chart.
    points = identity["element_modality"]
    assert len(points) == 10
    assert {p["point_key"] for p in points} == {"Lagna", "Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Ra", "Ke"}

    lagna_point = next(p for p in points if p["point_key"] == "Lagna")
    assert lagna_point["element_en"] == ELEMENT_NAMES_EN[SIGN_ELEMENT[chart["lagna_sign_index"]]]
    assert lagna_point["modality_en"] == MODALITY_NAMES_EN[SIGN_MODALITY[chart["lagna_sign_index"]]]

    for planet in chart["planets"]:
        point = next(p for p in points if p["point_key"] == planet["planet"])
        assert point["element_en"] == ELEMENT_NAMES_EN[SIGN_ELEMENT[planet["sign_index"]]]
        assert point["modality_en"] == MODALITY_NAMES_EN[SIGN_MODALITY[planet["sign_index"]]]


async def test_identity_varies_between_two_different_real_charts(client):
    """Same 'not static for every user' regression guard used elsewhere this
    session — two different birth charts must not produce an identical
    identity payload."""
    headers_a = await _signup_and_set_birth_data(client)
    resp_a = await client.get("/api/v1/kundali/identity", headers=headers_a)
    assert resp_a.status_code == 200, resp_a.text

    signup_b = await client.post(
        "/api/v1/auth/signup",
        json={"email": "identity-b@example.com", "password": "supersecret1", "name": "B", "preferred_language": "en"},
    )
    headers_b = {"Authorization": f"Bearer {signup_b.json()['access_token']}"}
    await client.put(
        "/api/v1/user/profile/birth-data",
        headers=headers_b,
        json={
            "name": "B", "date_of_birth": "1985-07-14", "time_of_birth": "14:10",
            "time_uncertain": False, "place_of_birth": "Mumbai, India",
            "latitude": 19.076, "longitude": 72.8777, "timezone_offset_hours": 5.5,
        },
    )
    resp_b = await client.get("/api/v1/kundali/identity", headers=headers_b)
    assert resp_b.status_code == 200, resp_b.text

    assert resp_a.json() != resp_b.json()


async def test_identity_requires_birth_profile(client):
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": "no-identity@example.com", "password": "supersecret1", "name": "No Birth", "preferred_language": "en"},
    )
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    resp = await client.get("/api/v1/kundali/identity", headers=headers)
    assert resp.status_code == 400
