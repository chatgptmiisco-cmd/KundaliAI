import pytest

from app.services.interpretation.prediction_templates import (
    life_event_reason_text,
    life_theme_text,
    marriage_window_reason_text,
    overall_year_theme,
    year_outlook_text,
    year_rating,
)


@pytest.mark.parametrize("language", ["en", "hi"])
def test_year_outlook_text_varies_by_real_dignity_and_house(language):
    strong = year_outlook_text(
        antardasha_lord="Ju", antardasha_lord_house=10, antardasha_lord_dignity="exalted",
        varsheshwar="Ve", varsheshwar_dignity="own_sign", muntha_house=11,
        jupiter_transit_house_from_moon=11, saturn_transit_house_from_moon=3,
        active_dosha_notes=[], language=language,
    )
    weak = year_outlook_text(
        antardasha_lord="Sa", antardasha_lord_house=8, antardasha_lord_dignity="debilitated",
        varsheshwar="Ma", varsheshwar_dignity="debilitated", muntha_house=12,
        jupiter_transit_house_from_moon=6, saturn_transit_house_from_moon=8,
        active_dosha_notes=["Saturn's Sade Sati is in its peak phase during this stretch."], language=language,
    )
    assert strong["theme"] != weak["theme"]
    assert strong["rating"] > weak["rating"]
    assert strong["opportunities"]
    assert weak["risks"]


def test_year_outlook_text_includes_dosha_notes_in_risks():
    note = "Saturn's Sade Sati is in its peak phase during this stretch."
    result = year_outlook_text(
        antardasha_lord="Mo", antardasha_lord_house=5, antardasha_lord_dignity="neutral",
        varsheshwar="Su", varsheshwar_dignity="neutral", muntha_house=3,
        jupiter_transit_house_from_moon=4, saturn_transit_house_from_moon=1,
        active_dosha_notes=[note], language="en",
    )
    assert note in result["risks"]


@pytest.mark.parametrize("language", ["en", "hi"])
def test_year_outlook_text_differs_by_transit_houses_even_with_identical_dasha_and_varshaphala_facts(language):
    """Regression guard: if the same Antardasha runs a whole year (common —
    some last several years), quarters must still read differently thanks to
    Jupiter/Saturn's own slower transit movement, not collapse to one
    repeated block."""
    common = dict(
        antardasha_lord="Ju", antardasha_lord_house=7, antardasha_lord_dignity="neutral",
        varsheshwar="Me", varsheshwar_dignity="neutral", muntha_house=9,
        active_dosha_notes=[], language=language,
    )
    q1 = year_outlook_text(jupiter_transit_house_from_moon=2, saturn_transit_house_from_moon=5, **common)
    q2 = year_outlook_text(jupiter_transit_house_from_moon=3, saturn_transit_house_from_moon=6, **common)
    assert q1["theme"] != q2["theme"]


def test_year_rating_rewards_strong_dignity_and_supportive_muntha():
    high = year_rating("exalted", "own_sign", muntha_house=10, active_dosha_count=0)
    low = year_rating("debilitated", "debilitated", muntha_house=8, active_dosha_count=2)
    assert 1 <= low <= high <= 10
    assert high > low


def test_year_rating_is_bounded():
    assert year_rating("exalted", "exalted", muntha_house=11, active_dosha_count=0) <= 10
    assert year_rating("debilitated", "debilitated", muntha_house=12, active_dosha_count=5) >= 1


@pytest.mark.parametrize("language", ["en", "hi"])
def test_overall_year_theme_varies_by_varsheshwar_and_muntha(language):
    a = overall_year_theme("Ju", "exalted", 10, language)
    b = overall_year_theme("Sa", "debilitated", 6, language)
    assert a != b
    assert len(a) > 10 and len(b) > 10


@pytest.mark.parametrize("language", ["en", "hi"])
def test_marriage_window_reason_text_composes_multiple_reasons(language):
    text = marriage_window_reason_text(
        reason_keys=["seventh_lord_antardasha", "venus_antardasha"],
        seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve",
        transit_corroborated=True,
        language=language,
    )
    assert "Venus" in text or "शुक्र" in text
    if language == "en":
        assert "Jupiter or Saturn" in text
    else:
        assert "गुरु या शनि" in text
    # Must lead with a real, plain-language effect (from _PERIOD_CONTENT), not
    # just the mechanism/jargon sentences.
    assert "Antardasha" not in text
    assert "Mahadasha" not in text


def test_marriage_window_reason_text_omits_corroboration_when_absent():
    text = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus", antardasha_lord="Ve",
        transit_corroborated=False, language="en",
    )
    assert "Jupiter or Saturn" not in text


@pytest.mark.parametrize("language", ["en", "hi"])
def test_marriage_window_reason_text_surfaces_natal_strength_when_given(language):
    strong = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language, natal_strength="strong",
    )
    weak = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language, natal_strength="weak",
    )
    plain = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language,
    )
    assert strong != weak != plain
    if language == "en":
        assert "well-placed in your birth chart" in strong
        assert "weakly placed in your birth chart" in weak
    else:
        assert "मज़बूत स्थिति में है" in strong
        assert "कमज़ोर स्थिति में है" in weak
    assert "well-placed" not in plain and "weakly placed" not in plain


@pytest.mark.parametrize("language", ["en", "hi"])
def test_marriage_window_reason_text_composes_the_dasha_relationship_note(language):
    same = marriage_window_reason_text(
        reason_keys=["venus_antardasha", "dasha_relationship_same"],
        seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language,
    )
    enemy = marriage_window_reason_text(
        reason_keys=["venus_antardasha", "dasha_relationship_enemy"],
        seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language,
    )
    plain = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language,
    )
    assert same != enemy != plain
    if language == "en":
        assert "same planet is running both" in same
        assert "natural enemies" in enemy
    else:
        assert "एक ही ग्रह के हाथ" in same
        assert "स्वाभाविक शत्रु" in enemy


@pytest.mark.parametrize("language", ["en", "hi"])
def test_marriage_window_reason_text_surfaces_retrograde_when_given(language):
    retro = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language, antardasha_lord_retrograde=True,
    )
    plain = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language, antardasha_lord_retrograde=False,
    )
    assert retro != plain
    if language == "en":
        assert "also retrograde right now" in retro
        assert "retrograde" not in plain
    else:
        assert "वक्री (retrograde) भी है" in retro
        assert "वक्री" not in plain
    # Purely informational — never a verdict either way.
    assert "not a verdict" in retro or "निर्णय नहीं" in retro


def test_marriage_window_reason_text_retrograde_note_reads_past_tense():
    future_text = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus", antardasha_lord="Ve",
        transit_corroborated=False, language="en", tense="future", antardasha_lord_retrograde=True,
    )
    past_text = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus", antardasha_lord="Ve",
        transit_corroborated=False, language="en", tense="past", antardasha_lord_retrograde=True,
    )
    assert future_text != past_text
    assert "is also retrograde right now" in future_text
    assert "was also retrograde during that period" in past_text


@pytest.mark.parametrize("language", ["en", "hi"])
def test_marriage_window_reason_text_surfaces_transit_obstruction_when_given(language):
    obstructed = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=True, language=language,
        transit_obstructing_planet="Mars" if language == "en" else "मंगल",
    )
    plain = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=True, language=language,
    )
    assert obstructed != plain
    if language == "en":
        assert "Mars is also transiting through" in obstructed
        assert "caution flag" in obstructed
        # Corroboration and obstruction are independent, not contradictory —
        # both sentences appear together.
        assert "second real signal" in obstructed
    else:
        assert "मंगल भी आपकी कुंडली" in obstructed
        assert "गुरु या शनि" in obstructed


def test_marriage_window_reason_text_obstruction_note_reads_past_tense():
    future_text = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus", antardasha_lord="Ve",
        transit_corroborated=False, language="en", tense="future", transit_obstructing_planet="Mars",
    )
    past_text = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus", antardasha_lord="Ve",
        transit_corroborated=False, language="en", tense="past", transit_obstructing_planet="Mars",
    )
    assert future_text != past_text
    assert "is also transiting through that same part of your chart" in future_text
    assert "was also transiting through that same part of your chart" in past_text


def test_life_event_reason_text_surfaces_transit_obstruction_when_given():
    obstructed = life_event_reason_text(
        "career", ["career_house_lord_antardasha"], "Saturn", antardasha_lord="Sa",
        transit_corroborated=False, language="en", transit_obstructing_planet="Rahu",
    )
    plain = life_event_reason_text(
        "career", ["career_house_lord_antardasha"], "Saturn", antardasha_lord="Sa",
        transit_corroborated=False, language="en",
    )
    assert obstructed != plain
    assert "Rahu is also transiting through" in obstructed


@pytest.mark.parametrize("language", ["en", "hi"])
def test_marriage_window_reason_text_surfaces_age_implausibility_when_given(language):
    early = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language, age_implausibility="early",
    )
    late = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language, age_implausibility="late",
    )
    plain = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language,
    )
    assert early != late != plain
    if language == "en":
        assert "earlier in life than marriage typically happens" in early
        assert "later in life than marriage typically happens" in late
    else:
        assert "विवाह" in early and "पहले" in early
        assert "विवाह" in late and "बाद" in late
    assert "typically happens" not in plain


def test_marriage_window_reason_text_age_implausibility_note_reads_past_tense():
    future_text = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus", antardasha_lord="Ve",
        transit_corroborated=False, language="en", tense="future", age_implausibility="early",
    )
    past_text = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus", antardasha_lord="Ve",
        transit_corroborated=False, language="en", tense="past", age_implausibility="early",
    )
    assert future_text != past_text
    assert "This window falls earlier in life than" in future_text
    assert "That window fell earlier in life than" in past_text


def test_life_event_reason_text_surfaces_age_implausibility_with_the_right_event_label():
    text = life_event_reason_text(
        "children", ["children_karaka_antardasha_Ju"], "Jupiter", antardasha_lord="Ju",
        transit_corroborated=False, language="en", age_implausibility="late",
    )
    assert "having children" in text
    assert "later in life" in text


@pytest.mark.parametrize("language", ["en", "hi"])
def test_marriage_window_reason_text_surfaces_reinterpretation_when_literal_event_implausible(language):
    plain = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language,
    )
    reinterpreted = marriage_window_reason_text(
        reason_keys=["venus_antardasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language, literal_event_plausible=False,
    )
    assert reinterpreted != plain
    if language == "en":
        assert "relationship or partnership-related development" in reinterpreted
        assert "relationship or partnership-related development" not in plain
    else:
        assert "रिश्ते या साझेदारी" in reinterpreted
        assert "रिश्ते या साझेदारी" not in plain


def test_life_event_reason_text_surfaces_reinterpretation_with_the_right_event_wording():
    wealth_text = life_event_reason_text(
        "wealth", ["wealth_house_lord_antardasha"], "Mercury", antardasha_lord="Me",
        transit_corroborated=False, language="en", literal_event_plausible=False,
    )
    children_text = life_event_reason_text(
        "children", ["children_karaka_antardasha_Ju"], "Jupiter", antardasha_lord="Ju",
        transit_corroborated=False, language="en", literal_event_plausible=False,
    )
    assert "family finances or shared household resources" in wealth_text
    assert "family or children's-welfare responsibility" in children_text


def test_life_event_reason_text_omits_reinterpretation_by_default():
    text = life_event_reason_text(
        "wealth", ["wealth_house_lord_antardasha"], "Mercury", antardasha_lord="Me",
        transit_corroborated=False, language="en",
    )
    assert "family finances" not in text


@pytest.mark.parametrize("language", ["en", "hi"])
def test_marriage_window_reason_text_surfaces_weak_evidence_when_flagged(language):
    plain = marriage_window_reason_text(
        reason_keys=["venus_mahadasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language,
    )
    weak = marriage_window_reason_text(
        reason_keys=["venus_mahadasha"], seventh_lord_name="Venus" if language == "en" else "शुक्र",
        antardasha_lord="Ve", transit_corroborated=False, language=language, evidence_level="backdrop_only",
    )
    assert weak != plain
    if language == "en":
        assert "broader multi-year period" in weak
        assert "broader multi-year period" not in plain
    else:
        assert "बड़ी बहु-वर्षीय" in weak
        assert "बड़ी बहु-वर्षीय" not in plain


def test_life_event_reason_text_surfaces_weak_evidence_when_flagged():
    text = life_event_reason_text(
        "wealth", ["wealth_karaka_mahadasha_Ju"], "Mercury", antardasha_lord="Ju",
        transit_corroborated=False, language="en", evidence_level="backdrop_only",
    )
    assert "broader multi-year period" in text


def test_life_event_reason_text_omits_weak_evidence_note_for_karaka_level_evidence():
    # A karaka's own Antardasha is real classical evidence, not backdrop-
    # only — it shouldn't carry the same caveat as a Mahadasha-only match.
    text = life_event_reason_text(
        "wealth", ["wealth_karaka_antardasha_Ju"], "Mercury", antardasha_lord="Ju",
        transit_corroborated=False, language="en", evidence_level="karaka_antardasha",
    )
    assert "broader multi-year period" not in text


def test_life_event_reason_text_omits_weak_evidence_note_by_default():
    text = life_event_reason_text(
        "wealth", ["wealth_house_lord_antardasha"], "Mercury", antardasha_lord="Me",
        transit_corroborated=False, language="en",
    )
    assert "broader multi-year period" not in text


@pytest.mark.parametrize("event_type,house_lord_name,house_lord_key", [
    ("career", "Saturn", "Sa"), ("wealth", "Jupiter", "Ju"), ("children", "Jupiter", "Ju"), ("foreign_travel", "Rahu", "Ra"),
])
@pytest.mark.parametrize("language", ["en", "hi"])
def test_life_event_reason_text_composes_house_lord_reason(event_type, house_lord_name, house_lord_key, language):
    text = life_event_reason_text(
        event_type=event_type,
        reason_keys=[f"{event_type}_house_lord_antardasha"],
        house_lord_name=house_lord_name,
        antardasha_lord=house_lord_key,
        transit_corroborated=False,
        language=language,
    )
    assert house_lord_name in text
    assert len(text) > 10
    assert "Antardasha" not in text
    assert "Mahadasha" not in text


def test_life_event_reason_text_composes_karaka_reasons_per_event_type():
    career_text = life_event_reason_text(
        "career", ["career_karaka_antardasha_Sa"], "Mercury", antardasha_lord="Sa",
        transit_corroborated=False, language="en"
    )
    wealth_text = life_event_reason_text(
        "wealth", ["wealth_karaka_antardasha_Ju"], "Mercury", antardasha_lord="Ju",
        transit_corroborated=False, language="en"
    )
    # Same planet (Ju/Sa are different here, but the point is the karaka
    # framing differs per event type) — texts must not collapse identically.
    assert career_text != wealth_text
    assert "Saturn" in career_text
    assert "Jupiter" in wealth_text


def test_life_event_reason_text_includes_corroboration_when_present():
    text = life_event_reason_text(
        "foreign_travel", ["foreign_travel_house_lord_antardasha"], "Rahu", antardasha_lord="Ra",
        transit_corroborated=True, language="en"
    )
    assert "second real signal" in text


def test_life_event_reason_text_omits_corroboration_when_absent():
    text = life_event_reason_text(
        "foreign_travel", ["foreign_travel_house_lord_antardasha"], "Rahu", antardasha_lord="Ra",
        transit_corroborated=False, language="en"
    )
    assert "second real signal" not in text


def test_life_event_reason_text_surfaces_natal_strength_when_given():
    strong = life_event_reason_text(
        "career", ["career_house_lord_antardasha"], "Saturn", antardasha_lord="Sa",
        transit_corroborated=False, language="en", natal_strength="strong",
    )
    weak = life_event_reason_text(
        "career", ["career_house_lord_antardasha"], "Saturn", antardasha_lord="Sa",
        transit_corroborated=False, language="en", natal_strength="weak",
    )
    plain = life_event_reason_text(
        "career", ["career_house_lord_antardasha"], "Saturn", antardasha_lord="Sa",
        transit_corroborated=False, language="en",
    )
    assert strong != weak != plain
    assert "well-placed in your birth chart" in strong
    assert "weakly placed in your birth chart" in weak
    assert "well-placed" not in plain and "weakly placed" not in plain


def test_life_event_reason_text_composes_the_dasha_relationship_note():
    friend = life_event_reason_text(
        "career", ["career_house_lord_antardasha", "dasha_relationship_friend"], "Saturn",
        antardasha_lord="Sa", transit_corroborated=False, language="en",
    )
    plain = life_event_reason_text(
        "career", ["career_house_lord_antardasha"], "Saturn",
        antardasha_lord="Sa", transit_corroborated=False, language="en",
    )
    assert friend != plain
    assert "natural friends" in friend
    assert "natural friends" not in plain


def test_life_event_reason_text_surfaces_retrograde_when_given():
    retro = life_event_reason_text(
        "career", ["career_house_lord_antardasha"], "Saturn", antardasha_lord="Sa",
        transit_corroborated=False, language="en", antardasha_lord_retrograde=True,
    )
    plain = life_event_reason_text(
        "career", ["career_house_lord_antardasha"], "Saturn", antardasha_lord="Sa",
        transit_corroborated=False, language="en", antardasha_lord_retrograde=False,
    )
    assert retro != plain
    assert "also retrograde right now" in retro
    assert "retrograde" not in plain


@pytest.mark.parametrize("language", ["en", "hi"])
def test_marriage_window_reason_text_past_tense_reads_retrospectively(language):
    future_text = marriage_window_reason_text(
        ["seventh_lord_antardasha"], "Mercury" if language == "en" else "बुध", antardasha_lord="Me",
        transit_corroborated=True, language=language, tense="future",
    )
    past_text = marriage_window_reason_text(
        ["seventh_lord_antardasha"], "Mercury" if language == "en" else "बुध", antardasha_lord="Me",
        transit_corroborated=True, language=language, tense="past",
    )
    assert future_text != past_text
    if language == "en":
        assert "has extra pull during this phase" in future_text
        assert "had extra pull during that phase" in past_text
    else:
        assert "सक्रिय है" in future_text and "सक्रिय था" in past_text


def test_life_event_reason_text_past_tense_reads_retrospectively():
    future_text = life_event_reason_text(
        "career", ["career_house_lord_antardasha"], "Mercury", antardasha_lord="Me",
        transit_corroborated=False, language="en", tense="future",
    )
    past_text = life_event_reason_text(
        "career", ["career_house_lord_antardasha"], "Mercury", antardasha_lord="Me",
        transit_corroborated=False, language="en", tense="past",
    )
    assert future_text != past_text
    assert "has extra pull during this phase" in future_text
    assert "had extra pull during that phase" in past_text


@pytest.mark.parametrize("language", ["en", "hi"])
def test_marriage_window_reason_text_dasha_relationship_note_reads_past_tense(language):
    future_text = marriage_window_reason_text(
        ["venus_antardasha", "dasha_relationship_enemy"],
        "Venus" if language == "en" else "शुक्र", antardasha_lord="Ve",
        transit_corroborated=False, language=language, tense="future",
    )
    past_text = marriage_window_reason_text(
        ["venus_antardasha", "dasha_relationship_enemy"],
        "Venus" if language == "en" else "शुक्र", antardasha_lord="Ve",
        transit_corroborated=False, language=language, tense="past",
    )
    assert future_text != past_text
    if language == "en":
        assert "results here can come with more friction" in future_text
        assert "results there came with more friction" in past_text
    else:
        assert "मिश्रित संकेत आ सकते हैं" in future_text
        assert "मिश्रित संकेत आए" in past_text


@pytest.mark.parametrize("language", ["en", "hi"])
def test_life_theme_text_composes_a_real_retrospective_theme(language):
    result = life_theme_text(
        mahadasha_lord="Sa", antardasha_lord="Ju", sade_sati_active=False, dhaiya_active=False, language=language,
    )
    assert 1 <= result["rating"] <= 10
    assert len(result["theme"]) > 20
    # Never a fabricated specific claim ("you got divorced") — only the
    # honest, computed thematic tendency.
    assert "you experienced" not in result["theme"].lower()


def test_life_theme_text_varies_with_different_lords():
    a = life_theme_text("Ju", "Ve", sade_sati_active=False, dhaiya_active=False, language="en")
    b = life_theme_text("Sa", "Ra", sade_sati_active=False, dhaiya_active=False, language="en")
    assert a["theme"] != b["theme"]


def test_life_theme_text_lowers_rating_and_adds_notes_when_sade_sati_or_dhaiya_active():
    baseline = life_theme_text("Ju", "Ve", sade_sati_active=False, dhaiya_active=False, language="en")
    with_hardship = life_theme_text("Ju", "Ve", sade_sati_active=True, dhaiya_active=True, language="en")
    assert with_hardship["rating"] <= baseline["rating"]
    assert "Sade Sati" in with_hardship["theme"]
    assert "Dhaiya" in with_hardship["theme"]
    assert "Sade Sati" not in baseline["theme"]
