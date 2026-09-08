"""Unit tests for chart_explanation_service — every yoga/dosha finding below
is hand-derived from a fully consistent Aries-Lagna fixture (each planet's
house is independently re-derived via house_number(sign, lagna=0) = sign+1,
matching the real whole-sign convention)."""
from app.astro.charts import ChartResult
from app.services.chart_explanation_service import build_house_breakdown, detect_yogas

_LAGNA_SIGN_INDEX = 0  # Aries

# Su=Leo(4)->house5, Mo=Aries(0)->house1, Ma=Aries(0)->house1 (own sign, Kendra
# -> Ruchaka), Me=Gemini(2)->house3 (own sign), Ju=Cancer(3)->house4 (exalted,
# Kendra -> Hamsa; also Kendra from Moon(0) -> Gajakesari), Ve=Libra(6)->house7
# (own sign, Kendra -> Malavya), Sa=Capricorn(9)->house10 (own sign, Kendra ->
# Sasa). Ra=Sagittarius(8)->house9, Ke=Gemini(2)->house3 (exactly opposite Ra).
_PLANET_SIGN_INDEX = {"Su": 4, "Mo": 0, "Ma": 0, "Me": 2, "Ju": 3, "Ve": 6, "Sa": 9, "Ra": 8, "Ke": 2}
_PLANET_HOUSE = {"Su": 5, "Mo": 1, "Ma": 1, "Me": 3, "Ju": 4, "Ve": 7, "Sa": 10, "Ra": 9, "Ke": 3}


def _fixture_chart() -> ChartResult:
    return ChartResult(
        chart_type="D1",
        lagna_sign_index=_LAGNA_SIGN_INDEX,
        lagna_longitude=5.0,
        planet_sign_index=_PLANET_SIGN_INDEX,
        planet_house=_PLANET_HOUSE,
        planet_retrograde={k: False for k in _PLANET_SIGN_INDEX},
        planet_longitude={k: v * 30.0 + 5 for k, v in _PLANET_SIGN_INDEX.items()},
    )


def test_house_breakdown_covers_all_twelve_houses_with_real_placements():
    breakdown = build_house_breakdown(_fixture_chart())
    assert len(breakdown) == 12
    by_house = {h["house"]: h for h in breakdown}

    # House 1 (Aries) holds Moon and Mars.
    assert set(by_house[1]["planets"]) == {"Mo", "Ma"}
    assert "Moon" in by_house[1]["explanation_en"]
    assert "Mars" in by_house[1]["explanation_en"]

    # House 2 (Taurus) is empty -> explanation names its lord (Venus) instead.
    assert by_house[2]["planets"] == []
    assert "Venus" in by_house[2]["explanation_en"]
    assert "शुक्र" in by_house[2]["explanation_hi"]


def test_detect_yogas_finds_gajakesari_and_all_relevant_mahapurusha_yogas():
    findings = detect_yogas(_fixture_chart())
    keys = {f["key"] for f in findings}

    assert "gajakesari" in keys
    # Mars (Aries), Mercury (Gemini... not own-sign-in-Kendra check needed),
    # Jupiter (exalted Cancer), Venus (own-sign Libra), Saturn (own-sign
    # Capricorn) are each in a Kendra house in their own/exalted sign.
    assert "mahapurusha_ma" in keys  # Ruchaka
    assert "mahapurusha_ju" in keys  # Hamsa
    assert "mahapurusha_ve" in keys  # Malavya
    assert "mahapurusha_sa" in keys  # Sasa


def test_detect_yogas_finds_conservative_raj_yoga():
    findings = detect_yogas(_fixture_chart())
    # House 4's lord (Moon) and house 1's lord (Mars) both physically sit in
    # house 1 -> a Kendra-lord/Trikona-lord conjunction.
    assert any(f["key"] == "raj_yoga" for f in findings)


def test_detect_yogas_finds_manglik():
    findings = detect_yogas(_fixture_chart())
    assert any(f["key"] == "manglik" for f in findings)


def test_detect_yogas_does_not_false_positive_kaal_sarp_or_kemadruma():
    findings = detect_yogas(_fixture_chart())
    keys = {f["key"] for f in findings}
    # This fixture's planets straddle both sides of the Rahu-Ketu axis, and
    # Kemadruma is cancelled by several Kendra-from-Moon placements — neither
    # should be (mis)reported as present.
    assert "kaal_sarp" not in keys
    assert "kemadruma" not in keys


def test_yoga_findings_have_bilingual_descriptions():
    findings = detect_yogas(_fixture_chart())
    assert findings  # this fixture is deliberately yoga-rich
    for f in findings:
        assert f["name_en"] and f["name_hi"]
        assert f["description_en"] and f["description_hi"]
        assert any(ord(ch) > 128 for ch in f["description_hi"])
