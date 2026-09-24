"""Locks in the hand-written per-Dasha-lord variety in the template
fallback — this is the offline stand-in for a live LLM call (see
app.services.interpretation.templates docstring), so it's worth verifying it
actually varies by lord rather than silently collapsing to one generic
sentence for everyone.
"""
import pytest

from app.astro.constants import VIMSHOTTARI_SEQUENCE
from app.services.interpretation.templates import (
    TemplateInterpreter,
    _LIFE_FRAMING_EN,
    _asked_about,
    _fuzzy_contains_phrase,
    _fuzzy_max_distance,
    _fuzzy_word_matches_keyword,
    _ordinal,
    _PERIOD_CONTENT_EN,
    _strip_trailing_stop,
    _TOPIC_KEYWORDS,
    detect_answering_rishi,
    message_mentions_career_timing,
    message_mentions_children_timing,
    message_mentions_foreign_travel_timing,
    message_mentions_marriage_timing,
    message_mentions_past_tense,
    message_mentions_wealth_timing,
    resolve_past_reference,
)

interpreter = TemplateInterpreter()


@pytest.mark.parametrize(
    "n,expected",
    [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (10, "10th"), (11, "11th"), (12, "12th"), (21, "21st")],
)
def test_ordinal_suffixes(n, expected):
    assert _ordinal(n) == expected


# --- Typo/spelling-variant tolerance ----------------------------------------

def test_fuzzy_word_matches_keyword_basic_cases():
    assert _fuzzy_word_matches_keyword("shaadi", "shaadi")  # identical
    assert _fuzzy_word_matches_keyword("shadi", "shaadi")  # missing letter
    # "sitten" vs "kitten" is only a 1-letter substitution, but the first
    # letters differ — the same-first-letter guard rejects it regardless of
    # how close the edit distance is (see _fuzzy_word_matches_keyword).
    assert not _fuzzy_word_matches_keyword("sitten", "kitten")


def test_fuzzy_word_matches_keyword_tolerates_transpositions():
    """rapidfuzz's Damerau-Levenshtein distance (unlike plain Levenshtein)
    counts an adjacent-letter swap as ONE edit — so "marraige" (transposed
    i/a) matches "marriage" even though a naive Levenshtein distance of 2
    would have put it just outside the 6-8 letter keyword's tolerance of 2...
    this specific case previously worked by coincidence (2 <= 2); the real
    point of this test is documenting that the distance metric itself now
    understands transpositions as cheap, not just wide buckets."""
    assert _fuzzy_word_matches_keyword("marraige", "marriage")


def test_fuzzy_contains_phrase_tolerates_a_typo_in_either_word():
    words = "sarkari nokri kab lagegi".split()
    assert _fuzzy_contains_phrase(words, ["sarkari", "naukri"])
    assert not _fuzzy_contains_phrase(words, ["green", "card"])


def test_h1b_routes_to_foreign_travel_timing():
    assert message_mentions_foreign_travel_timing("when will I get my h1b?")


@pytest.mark.parametrize("message", ["will I get a loan approved?", "when will my debt be cleared?", "kab hoga nivesh se fayda"])
def test_new_money_keywords_route_to_wealth_timing(message):
    assert message_mentions_wealth_timing(message)


@pytest.mark.parametrize("message", ["will I need surgery this year", "when will my accident risk go away"])
def test_new_health_keywords_are_recognized(message):
    assert _asked_about(message, _TOPIC_KEYWORDS["health"])


@pytest.mark.parametrize("message", ["will I ever buy property", "when will I get a car", "vehicle milega kya"])
def test_new_family_keywords_are_recognized(message):
    assert _asked_about(message, _TOPIC_KEYWORDS["family"])


def test_car_keyword_does_not_collide_with_career():
    """Regression guard: "car" is word-boundary matched, so it must not
    fire on "career" (which contains "car" as a substring, not a standalone
    word) — otherwise every career question would wrongly also read as a
    vehicle/property question."""
    assert not _asked_about("how is my career looking", _TOPIC_KEYWORDS["family"])


def test_board_exam_and_college_admission_are_recognized():
    assert _asked_about("when is my board exam going well", _TOPIC_KEYWORDS["education"])
    assert _asked_about("will I get college admission this year", _TOPIC_KEYWORDS["education"])


# --- Answering-rishi attribution (for the frontend's "answered by X" label) -

def test_detect_answering_rishi_names_the_real_specialist():
    assert detect_answering_rishi("Tell me about my marriage prospects") == "gargi"
    assert detect_answering_rishi("How is my career looking?") == "bhrigu"
    assert detect_answering_rishi("Am I manglik?") == "agastya"


def test_detect_answering_rishi_returns_none_for_an_unmatched_message():
    assert detect_answering_rishi("just saying hello") is None


def test_fuzzy_max_distance_scales_with_keyword_length():
    assert _fuzzy_max_distance(2) == 0  # too short to fuzz safely at all
    assert _fuzzy_max_distance(3) == 0  # "din"/"did"/"in" collision — see below
    assert _fuzzy_max_distance(5) == 1
    assert _fuzzy_max_distance(6) == 2
    assert _fuzzy_max_distance(8) == 2


@pytest.mark.parametrize(
    "message",
    [
        "shadi kab hogi",  # missing double-a
        "shadi kb hogi",  # missing double-a AND vowel-dropped kab
        "when will i get marraige",  # transposed letters
    ],
)
def test_marriage_timing_tolerates_real_typos(message):
    assert message_mentions_marriage_timing(message)


@pytest.mark.parametrize("message", ["nokri kab milegi", "carreer kab badlega"])
def test_career_timing_tolerates_real_typos(message):
    assert message_mentions_career_timing(message)


def test_children_timing_tolerates_a_real_typo():
    assert message_mentions_children_timing("when will i have childern")


def test_foreign_travel_timing_tolerates_a_real_typo():
    assert message_mentions_foreign_travel_timing("when will my imigration come through")


def test_fuzzy_matching_does_not_reintroduce_the_din_in_collision():
    """Regression guard for a real bug caught while building this: "din"
    (today/day keyword, 3 letters) was fuzzy-matching the extremely common
    word "in" at edit-distance 1 — before the length-3 floor was added,
    almost every message containing "in" was wrongly classified as a
    "today" question."""
    assert not message_mentions_past_tense("please tell me about my career in general")


def test_fuzzy_matching_does_not_confuse_dasha_with_dosha():
    """Regression guard for a real collision caught live: "dasha" and
    "dosha" (and their plurals "dashas"/"doshas") sit at edit-distance 1-2
    of each other, so a plain "what dasha am I running" question was also
    wrongly matching the "dosha" category and pulling in an unrelated
    Manglik-dosha finding. All four are exact-only now (see
    _NO_FUZZY_KEYWORDS)."""
    from app.services.interpretation.templates import _DOSHA_KEYWORDS

    assert not _asked_about("what dasha am i running right now", _DOSHA_KEYWORDS)


def test_fuzzy_matching_does_not_confuse_did_with_din():
    """Regression guard for the second real collision caught: "did" (a
    past-tense keyword) is itself edit-distance 1 from "din" (a today
    keyword), same first letter — both are exactly 3 letters, which is
    exactly why 3-letter keywords are excluded from fuzzing entirely rather
    than trying to special-case every short collision as it's found."""
    from app.services.interpretation.templates import _asked_about, _TODAY_KEYWORDS

    assert not _asked_about("did i have a good career period", _TODAY_KEYWORDS)


def test_strip_trailing_stop_removes_terminal_punctuation_only():
    assert _strip_trailing_stop("Something clear.") == "Something clear"


# --- Past-event reflection: tense detection + date resolution --------------

def test_message_mentions_past_tense_recognizes_real_phrasings():
    assert message_mentions_past_tense("Why did my marriage get delayed?")
    assert message_mentions_past_tense("What happened to me in 2016?")
    assert message_mentions_past_tense("Was there a reason for that setback?")
    assert not message_mentions_past_tense("When will I get married?")
    assert not message_mentions_past_tense("How's my career looking?")


def test_resolve_past_reference_parses_an_explicit_year():
    resolved = resolve_past_reference("What happened to me in 2016?", birth_year=1990, current_year=2026)
    assert resolved is not None
    assert resolved.year == 2016


def test_resolve_past_reference_parses_years_ago():
    resolved = resolve_past_reference("Why was I struggling 5 years ago?", birth_year=1990, current_year=2026)
    assert resolved is not None
    assert resolved.year == 2021


def test_resolve_past_reference_parses_when_i_was_age():
    resolved = resolve_past_reference("What happened when I was 25?", birth_year=1990, current_year=2026)
    assert resolved is not None
    assert resolved.year == 2015


def test_resolve_past_reference_returns_none_when_unresolvable():
    assert resolve_past_reference("Why did things feel so hard?", birth_year=1990, current_year=2026) is None


def test_resolve_past_reference_rejects_years_outside_the_persons_lifetime():
    # A "year" mentioned before birth or after "now" isn't a resolvable
    # reference to this person's own past — never guessed.
    assert resolve_past_reference("What about 1985?", birth_year=1990, current_year=2026) is None
    assert resolve_past_reference("What about 2030?", birth_year=1990, current_year=2026) is None
    assert _strip_trailing_stop("कुछ बात।") == "कुछ बात"
    assert _strip_trailing_stop("No punctuation here") == "No punctuation here"


async def test_complete_kundali_sections_vary_by_real_house_lord_placements():
    # Two charts sharing the same lagna and mahadasha lord, but with different
    # house-lord placements, must not produce identical section text — this
    # is the real per-chart variety the "static for every user" bug was
    # missing (previously only lagna sign + mahadasha lord mattered).
    base_context = {
        "lagna_sign": "Aries", "moon_sign": "Cancer", "mahadasha_lord_key": "Ju", "mahadasha_lord": "Jupiter",
        "is_manglik": False,
    }
    context_a = {
        **base_context,
        "lagna_lord_key": "Ma", "lagna_lord_house": 3, "lagna_lord_dignity": "own_sign",
        "tenth_lord_key": "Sa", "tenth_lord_house": 7, "tenth_lord_dignity": "neutral",
        "seventh_lord_key": "Ve", "seventh_lord_house": 1, "seventh_lord_dignity": "exalted",
        "sixth_lord_key": "Mo", "sixth_lord_house": 9, "sixth_lord_dignity": "debilitated",
    }
    context_b = {
        **base_context,
        "lagna_lord_key": "Ma", "lagna_lord_house": 9, "lagna_lord_dignity": "debilitated",
        "tenth_lord_key": "Sa", "tenth_lord_house": 2, "tenth_lord_dignity": "own_sign",
        "seventh_lord_key": "Ve", "seventh_lord_house": 5, "seventh_lord_dignity": "neutral",
        "sixth_lord_key": "Mo", "sixth_lord_house": 11, "sixth_lord_dignity": "exalted",
    }
    result_a = await interpreter.complete_kundali(context_a, "en", "simple")
    result_b = await interpreter.complete_kundali(context_b, "en", "simple")

    for section_id in ("personality_nature", "career_money", "relationships_marriage", "health_temperament"):
        summary_a = result_a["sections"][section_id]["summary"]
        summary_b = result_b["sections"][section_id]["summary"]
        assert summary_a != summary_b, f"{section_id} did not vary despite different house-lord placements"


async def test_complete_kundali_strengths_challenges_summary_has_no_stray_punctuation():
    context = {
        "lagna_sign": "Aries", "moon_sign": "Cancer", "mahadasha_lord_key": "Ra", "mahadasha_lord": "Rahu",
        "is_manglik": False,
    }
    result = await interpreter.complete_kundali(context, "en", "simple")
    summary = result["sections"]["strengths_challenges"]["summary"]
    assert ". is your strength" not in summary
    assert ". is your challenge" not in summary


@pytest.mark.parametrize("lord", VIMSHOTTARI_SEQUENCE)
async def test_period_analysis_covers_every_lord_distinctly(lord):
    context = {
        "mahadasha_lord_key": lord, "mahadasha_lord": lord,
        "antardasha_lord_key": lord, "antardasha_lord": lord,
    }
    result = await interpreter.period_analysis(context, "en", "simple")
    assert 1 <= result["rating"] <= 10
    assert len(result["risks"]) == 2
    assert len(result["opportunities"]) == 2
    assert result["summary"]
    # risks and opportunities must not be the same text for any lord
    assert set(result["risks"]).isdisjoint(result["opportunities"])


async def test_period_analysis_one_liners_are_all_distinct_across_lords():
    summaries = set()
    for lord in VIMSHOTTARI_SEQUENCE:
        context = {"mahadasha_lord_key": lord, "mahadasha_lord": lord, "antardasha_lord_key": lord, "antardasha_lord": lord}
        result = await interpreter.period_analysis(context, "en", "simple")
        summaries.add(result["summary"])
    assert len(summaries) == len(VIMSHOTTARI_SEQUENCE)


async def test_period_analysis_rating_weights_antardasha_more_than_mahadasha():
    # Jupiter (rating 8) as antardasha inside a Saturn (rating 5) mahadasha
    # should land closer to 8 than to 5, since antardasha is weighted 2:1.
    context = {
        "mahadasha_lord_key": "Sa", "mahadasha_lord": "Saturn",
        "antardasha_lord_key": "Ju", "antardasha_lord": "Jupiter",
    }
    result = await interpreter.period_analysis(context, "en", "simple")
    assert result["rating"] >= 6


@pytest.mark.parametrize("lord", VIMSHOTTARI_SEQUENCE)
async def test_complete_kundali_brutal_truth_varies_by_mahadasha_lord(lord):
    context = {"lagna_sign": "Taurus", "moon_sign": "Cancer", "mahadasha_lord_key": lord, "mahadasha_lord": lord, "is_manglik": False}
    result = await interpreter.complete_kundali(context, "en", "simple")
    assert result["brutal_truth"]
    assert result["core_strength"]
    assert result["core_challenge"]


async def test_complete_kundali_brutal_truths_are_all_distinct_across_lords():
    truths = set()
    for lord in VIMSHOTTARI_SEQUENCE:
        context = {"lagna_sign": "Taurus", "moon_sign": "Cancer", "mahadasha_lord_key": lord, "mahadasha_lord": lord, "is_manglik": False}
        result = await interpreter.complete_kundali(context, "en", "simple")
        truths.add(result["brutal_truth"])
    assert len(truths) == len(VIMSHOTTARI_SEQUENCE)


async def test_hindi_period_analysis_also_covers_every_lord():
    for lord in VIMSHOTTARI_SEQUENCE:
        context = {"mahadasha_lord_key": lord, "mahadasha_lord": lord, "antardasha_lord_key": lord, "antardasha_lord": lord}
        result = await interpreter.period_analysis(context, "hi", "simple")
        assert result["summary"]
        assert len(result["risks"]) == 2
        assert len(result["opportunities"]) == 2


async def test_strengths_challenges_mentions_actual_strongest_and_weakest_planet():
    context = {
        "lagna_sign": "Taurus", "moon_sign": "Cancer", "mahadasha_lord_key": "Mo", "mahadasha_lord": "Moon",
        "is_manglik": False, "strongest_planet_key": "Su", "weakest_planet_key": "Sa",
    }
    result = await interpreter.complete_kundali(context, "en", "simple")
    key_points = " ".join(result["sections"]["strengths_challenges"]["key_points"])
    assert "Sun" in key_points
    assert "Saturn" in key_points


async def test_core_strength_and_challenge_follow_dignity_not_only_mahadasha_lord():
    # Two charts sharing the SAME current Mahadasha lord (Moon) but with
    # different dignity findings must NOT get identical core_strength/
    # core_challenge — this is exactly the "static for every user" bug:
    # before this fix, both fields were keyed to maha_key alone (9 possible
    # values total), so any two users currently running the same Mahadasha
    # saw word-for-word identical text regardless of their actual charts.
    shared_maha = {"lagna_sign": "Taurus", "moon_sign": "Cancer", "mahadasha_lord_key": "Mo", "mahadasha_lord": "Moon", "is_manglik": False}
    context_a = {**shared_maha, "strongest_planet_key": "Su", "weakest_planet_key": "Sa"}
    context_b = {**shared_maha, "strongest_planet_key": "Ju", "weakest_planet_key": "Ma"}
    context_balanced = {**shared_maha, "strongest_planet_key": None, "weakest_planet_key": None}

    result_a = await interpreter.complete_kundali(context_a, "en", "simple")
    result_b = await interpreter.complete_kundali(context_b, "en", "simple")
    result_balanced = await interpreter.complete_kundali(context_balanced, "en", "simple")

    assert result_a["core_strength"] != result_b["core_strength"]
    assert result_a["core_challenge"] != result_b["core_challenge"]
    # brutal_truth stays tied to the current Mahadasha lord regardless (it's
    # about the present chapter of life, not the chart's fixed structure).
    assert result_a["brutal_truth"] == result_b["brutal_truth"] == result_balanced["brutal_truth"]
    # A chart with no exalted/debilitated planet falls back to the Mahadasha
    # lord's own framing rather than crashing or leaving the field empty.
    moon_framing = _LIFE_FRAMING_EN["Mo"]
    assert result_balanced["core_strength"] == moon_framing["core_strength"]
    assert result_balanced["core_challenge"] == moon_framing["core_challenge"]


async def test_strengths_challenges_falls_back_gracefully_with_no_extreme_planet():
    context = {
        "lagna_sign": "Taurus", "moon_sign": "Cancer", "mahadasha_lord_key": "Mo", "mahadasha_lord": "Moon",
        "is_manglik": False, "strongest_planet_key": None, "weakest_planet_key": None,
    }
    result = await interpreter.complete_kundali(context, "en", "simple")
    key_points = result["sections"]["strengths_challenges"]["key_points"]
    assert "balanced chart" in key_points[-1]


# --- chat_reply: deterministic free-text Q&A routing -----------------------
# Replaces a stub that ignored the user's question and always asked them to
# clarify. These lock in that real questions get real, chart-grounded
# answers built from facts the app already computes elsewhere (house
# breakdown text, yoga/dosha findings, current dasha, today's reading) —
# never an invented fact.

_CHAT_CONTEXT = {
    "lagna_sign": "Sagittarius",
    "house_breakdown": {
        10: "Mercury sits here, bringing a mentally busy quality — this house governs career.",
        7: "No planet sits here — relationships depend on Mercury, this house's lord.",
    },
    # Plain verdict per house — this (not house_breakdown above) is what a
    # static topic chat answer actually returns; see
    # chart_explanation_service._VERDICT_BY_HOUSE_EN/HI.
    # Matches production shape: chart_explanation_service.build_house_
    # breakdown concatenates the per-house verdict with a fixed per-bucket
    # "reason" clause (_VERDICT_REASON_EN) into one string.
    "house_verdict": {
        10: "Your career may have both good phases and hard phases. There's no strong push in either "
        "direction right now, so a lot depends on your own effort and choices.",
        7: "Your relationships may have both good and hard moments. There's no strong push in either "
        "direction right now, so a lot depends on your own effort and choices.",
    },
    "yogas": [
        {
            "key": "gajakesari",
            "name": "Gajakesari Yoga",
            "description": "Moon and Jupiter in mutual Kendra houses.",
            "chat_summary": "Yes, you have Gajakesari Yoga.",
        },
        {
            "key": "manglik",
            "name": "Manglik (Mangal) Dosha",
            "description": "Mars sits in a Manglik-checked house.",
            "chat_summary": "Yes, you are Manglik.",
        },
    ],
    "mahadasha_lord": "Jupiter",
    "antardasha_lord": "Saturn",
    "daily_reading": {
        "rating_reason": "Running Saturn Antardasha, Moon transiting your 8th house.",
        "brutal_truth": "Today leans toward unexpected change.",
        "festival": "Diwali",
    },
}


def _history(message: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": message}]


async def test_chat_reply_answers_career_question_from_real_house_ten_text():
    reply = await interpreter.chat_reply(_history("How's my career looking this year?"), _CHAT_CONTEXT, "en")
    assert reply == _CHAT_CONTEXT["house_verdict"][10]


async def test_chat_reply_answers_marriage_question_from_real_house_seven_text():
    reply = await interpreter.chat_reply(_history("Tell me about my marriage prospects"), _CHAT_CONTEXT, "en")
    assert reply == _CHAT_CONTEXT["house_verdict"][7]


async def test_chat_reply_answers_hindi_career_question():
    reply = await interpreter.chat_reply(_history("मेरा करियर कैसा रहेगा?"), _CHAT_CONTEXT, "hi")
    assert reply == _CHAT_CONTEXT["house_verdict"][10]


async def test_marriage_timing_blocks_the_full_breakdown_for_an_already_married_user():
    """Regression guard for a real, reproduced bug: an explicit, direct
    "shaadi kab hogi" (when will marriage happen) from an ALREADY MARRIED
    user got the FULL detailed first-marriage breakdown (dates, natal
    strength, retrograde, D9, evidence level, age estimate) with only a
    single reframe sentence buried inside — this eligibility check must be
    enforced every time, not just the first time in a conversation (that's
    conversation_engine's separate, one-time "marriage_clarified" gate,
    which this does NOT depend on)."""
    context = {
        **_CHAT_CONTEXT, "detected_categories": ["marriage_timing"],
        "life_state": {"marital_status": "married"},
        "marriage_timing_direction": "future",
        "marriage_timing_windows": [{
            "start_date": "2025-10-31", "end_date": "2028-09-06", "mahadasha_lord_name": "Saturn",
            "antardasha_lord_name": "Saturn", "score": 5, "evidence_level": "house_lord_antardasha",
            "reason": "Saturn is running.", "transit_corroborated": False,
        }],
    }
    reply = await interpreter.chat_reply(_history("shaadi kab hogi"), context, "en")
    assert "already married" in reply.lower()
    assert "2025-10-31" not in reply
    assert "retrograde" not in reply.lower()
    assert "evidence" not in reply.lower()

    # A PAST marriage-timing question is still a sensible ask regardless of
    # current status (e.g. "what led to my actual marriage") — not blocked.
    past_context = {**context, "marriage_timing_direction": "past"}
    past_reply = await interpreter.chat_reply(_history("meri shaadi kab hui thi"), past_context, "en")
    assert "already married" not in past_reply.lower()


def test_house_technical_hint_names_the_real_sign_lord_and_placement():
    from app.services.interpretation.templates import _house_technical_hint

    context = {
        "house_technical": {
            10: {"house_sign": "Taurus", "planet_name": "Venus", "rules_houses": [4, 11], "placed_house": 4, "placed_sign": "Scorpio"},
        }
    }
    hint = _house_technical_hint("career", context, hi=False)
    assert hint == "Your 10th house is Taurus, ruled by Venus, currently placed in your 4th house (Scorpio)."


def test_house_technical_hint_avoids_repeating_the_same_house_when_the_lord_sits_in_its_own_house():
    from app.services.interpretation.templates import _house_technical_hint

    context = {
        "house_technical": {
            10: {"house_sign": "Taurus", "planet_name": "Venus", "rules_houses": [10], "placed_house": 10, "placed_sign": "Taurus"},
        }
    }
    hint = _house_technical_hint("career", context, hi=False)
    assert hint == "Your 10th house is Taurus, and its ruler Venus sits right there too."
    assert hint.count("10th house") == 1


def test_house_technical_hint_applies_to_topics_with_no_timing_engine_too():
    from app.services.interpretation.templates import _house_technical_hint

    context = {"house_technical": {6: {"house_sign": "Aries", "planet_name": "Mars", "rules_houses": [1, 6], "placed_house": 6, "placed_sign": "Aries"}}}
    assert _house_technical_hint("health", context, hi=False) is not None


def test_house_technical_hint_is_none_without_data():
    from app.services.interpretation.templates import _house_technical_hint

    assert _house_technical_hint("career", {}, hi=False) is None


async def test_chat_reply_career_topic_answer_omits_house_technical_facts_by_default():
    """Phase 12 — jargon control: house/sign/planet names only render when
    the user actually asks a technical question (see wants_technical_detail).
    A plain "how's my career looking" no longer gets "Taurus, ruled by
    Venus" unasked-for — that was the exact live complaint."""
    context = {**_CHAT_CONTEXT, "house_technical": {
        10: {"house_sign": "Taurus", "planet_name": "Venus", "rules_houses": [4, 11], "placed_house": 4, "placed_sign": "Scorpio"},
    }}
    reply = await interpreter.chat_reply(_history("How's my career looking this year?"), context, "en")
    assert reply.startswith(_CHAT_CONTEXT["house_verdict"][10])
    assert "Taurus" not in reply and "Venus" not in reply


async def test_chat_reply_career_topic_answer_includes_house_technical_facts_when_asked():
    context = {**_CHAT_CONTEXT, "house_technical": {
        10: {"house_sign": "Taurus", "planet_name": "Venus", "rules_houses": [4, 11], "placed_house": 4, "placed_sign": "Scorpio"},
    }}
    reply = await interpreter.chat_reply(_history("Why is my career like this? Which house is it?"), context, "en")
    assert "Taurus" in reply and "Venus" in reply and "Scorpio" in reply


def test_life_context_hint_surfaces_a_known_fact_for_the_matching_domain():
    from app.services.interpretation.templates import _life_context_hint

    context = {"life_context": {"career": {"employer_type": {"value": "works at a startup", "confidence": "high"}}}}
    hint = _life_context_hint("career", context, hi=False)
    assert hint == "Worth keeping in mind, from what you've shared before: works at a startup."


def test_life_context_hint_is_none_without_a_matching_fact_or_domain_mapping():
    from app.services.interpretation.templates import _life_context_hint

    assert _life_context_hint("career", {"life_context": {}}, hi=False) is None
    assert _life_context_hint("career", {"life_context": {"money": {"k": {"value": "x"}}}}, hi=False) is None
    # "health" has no life_context domain mapping at all.
    assert _life_context_hint("health", {"life_context": {"identity": {"k": {"value": "x"}}}}, hi=False) is None


async def test_chat_reply_career_topic_answer_includes_a_known_life_context_fact():
    context = {**_CHAT_CONTEXT, "life_context": {"career": {"employer_type": {"value": "works at a startup"}}}}
    reply = await interpreter.chat_reply(_history("How's my career looking this year?"), context, "en")
    assert reply.startswith(_CHAT_CONTEXT["house_verdict"][10])
    assert "works at a startup" in reply


async def test_chat_reply_uses_age_band_lead_in_when_no_fact_is_known():
    """Phase 13 (Stage 2) — Life Stage Awareness: with no known occupation or
    business fact to ground a reframe, an age-appropriate framing still
    leads the reply instead of a one-size-fits-all verdict for every age."""
    context = {**_CHAT_CONTEXT, "user_age": 22}
    reply = await interpreter.chat_reply(_history("How's my career looking this year?"), context, "en")
    assert reply.startswith("At this stage, career questions are usually more about direction")
    older_context = {**_CHAT_CONTEXT, "user_age": 55}
    older_reply = await interpreter.chat_reply(_history("How's my career looking this year?"), older_context, "en")
    assert older_reply.startswith("At this stage, career questions are more often about leadership")


async def test_chat_reply_known_fact_still_takes_precedence_over_age_band():
    """An age band is a real signal but weaker than an actual stated fact —
    when both are available, only the fact-based reframe should lead, not
    both stacked together."""
    context = {
        **_CHAT_CONTEXT, "user_age": 22,
        "life_context": {"career": {"occupation": {"value": "developer", "source": "user_stated", "confidence": "high"}}},
    }
    reply = await interpreter.chat_reply(_history("How's my career looking this year?"), context, "en")
    assert reply.startswith("Since you work as developer")
    assert "At this stage, career questions" not in reply


async def test_chat_reply_age_band_extends_to_a_previously_uncovered_topic():
    """Stage 2 — the remaining 5 lower-traffic topics (health, education,
    friends, travel, siblings) had zero context-aware framing before this;
    age-banding is the mechanical fix that now reaches all of them."""
    context = {**_CHAT_CONTEXT, "user_age": 22, "house_verdict": {**_CHAT_CONTEXT["house_verdict"], 6: "Your health may be fine at times and weak at other times."}}
    reply = await interpreter.chat_reply(_history("How's my health looking?"), context, "en")
    assert reply.startswith("At this age, health questions are usually about building good habits")


async def test_chat_reply_relationship_conflict_references_the_actual_stated_concern():
    """Regression guard for a real, reproduced bug: a distress/conflict
    message got the exact same flat "your relationships may have good and
    hard moments" line a neutral status check would — once the concern
    itself is known (see conversation_engine's concern_type gate, asked
    before this point is reached), the reply should name it directly
    instead of staying generic, and never tack on an irrelevant marriage-
    timing window."""
    context = {
        **_CHAT_CONTEXT, "detected_categories": ["relationship_conflict"],
        "life_context": {"relationships": {"concern_type": {"value": "we keep having the same argument about money"}}},
    }
    reply = await interpreter.chat_reply(_history("main shaadi se dukhi hoon"), context, "en")
    assert "we keep having the same argument about money" in reply
    assert "may have both good and hard moments" not in reply
    assert "window for marriage" not in reply


async def test_chat_reply_relationship_conflict_pulls_in_real_chart_specific_content():
    """Regression guard for a real, reproduced complaint: even after naming
    the stated concern, the CLOSING line was itself a fixed template ("a
    chart alone can't resolve this... good time for patience") with zero
    actual chart content — exactly the "friend based on charts and
    astrology, not a template" complaint. Must now pull in the SAME real,
    planet-specific period content the "dasha" category already uses,
    keyed by whichever planet is ACTUALLY running for this person — not a
    fixed sentence regardless of their chart."""
    context = {
        **_CHAT_CONTEXT, "detected_categories": ["relationship_conflict"], "antardasha_lord_code": "Sa",
        "life_context": {"relationships": {"concern_type": {"value": "we keep having the same fight"}}},
    }
    reply = await interpreter.chat_reply(_history("main shaadi se dukhi hoon"), context, "en")
    assert "we keep having the same fight" in reply
    # The real Saturn one_liner from _PERIOD_CONTENT_EN, not a generic close.
    assert "grind, not a disaster" in reply
    assert "a chart alone can't resolve" in reply  # acknowledgment stays, just no longer the ENTIRE content


async def test_generic_house_verdict_gets_a_real_period_specific_addition():
    """Regression guard for a real, reproduced complaint: once natal dignity
    is neutral (the most common case — no exalted/debilitated/own-sign
    planet involved) and nothing else grounds the answer, the ENTIRE reply
    used to be just the flat, house-generic verdict sentence — "Your
    relationships may have both good and hard moments." — near-identical in
    shape to every other domain's own neutral verdict ("both good phases
    and hard phases" for career, "both gains and losses" for money), with
    zero content that actually varies by person. User's own words: "if
    there's no push either way, why do I need an astrologer?" Must now also
    carry the real, current-dasha-lord-specific one-liner, exactly like
    relationship_conflict's own concern_sentence already does — this is the
    generic case, not the concern-known one, so no concern_type is set."""
    context = {
        **_CHAT_CONTEXT, "detected_categories": ["marriage"], "antardasha_lord_code": "Sa",
        "life_state": {"marital_status": "married"},
    }
    reply = await interpreter.chat_reply(_history("tell me about my marriage"), context, "en")
    assert "may have both good and hard moments" in reply  # the honest verdict stays
    assert "grind, not a disaster" in reply  # the real Saturn one_liner, newly added
    # The fixed, house-agnostic "no strong push either way, depends on your
    # effort" reason clause is dropped once real content replaces it — it
    # would otherwise sit right before the real one-liner as pure hedging.
    assert "no strong push in either direction" not in reply


async def test_generic_house_verdict_addition_is_skipped_when_a_real_timing_window_already_fired():
    """The period one-liner is a fallback for when NOTHING else grounds the
    answer — an unmarried user's bare marriage question already gets a real
    forward-looking timing window (marriage_timing_windows), so piling the
    same antardasha one-liner on top would be redundant, not helpful."""
    context = {
        **_CHAT_CONTEXT, "detected_categories": ["marriage"], "antardasha_lord_code": "Sa",
        "life_state": {"marital_status": "single"},
        "marriage_timing_windows": [{
            "start_date": "2027-01-01", "end_date": "2028-06-01", "mahadasha_lord_name": "Venus",
            "antardasha_lord_name": "Venus", "score": 5, "evidence_level": "house_lord_antardasha",
        }],
    }
    reply = await interpreter.chat_reply(_history("tell me about my marriage"), context, "en")
    if "grind, not a disaster" in reply:
        assert False, "period one-liner should be skipped once a real timing window already grounds the answer"


async def test_chat_reply_family_planning_framing_fires_from_the_category_alone():
    """Regression guard for a real, reproduced bug: picking "family
    planning" from the married-status menu (a category selection, not a
    full sentence like "we are planning a family") still got the plain
    "married life" reframe instead of a family-planning-aware one, because
    the framing only checked for a separately-EXTRACTED historical fact —
    the current question itself being family_planning is real evidence too."""
    context = {**_CHAT_CONTEXT, "detected_categories": ["family_planning"], "life_state": {"marital_status": "married"}}
    reply = await interpreter.chat_reply(_history("yes, Family planning"), context, "en")
    assert "thinking about family planning" in reply.lower()
    assert "family growth" in reply.lower()


async def test_chat_reply_relationship_conflict_falls_back_honestly_without_a_known_concern():
    """Without a known concern to reference, the honest fallback is the
    plain verdict (still fronted by the sub-intent's own naming lead-in) —
    never a fabricated concern."""
    context = {**_CHAT_CONTEXT, "detected_categories": ["relationship_conflict"]}
    reply = await interpreter.chat_reply(_history("main shaadi se dukhi hoon"), context, "en")
    assert _CHAT_CONTEXT["house_verdict"][7] in reply


def test_topic_timing_hint_appends_the_real_window_to_a_plain_topic_answer():
    """The actual fix for "generic answer that shows nothing about the
    question": chat.py already auto-fetches the topic's timing counterpart
    windows in the background (see _TOPIC_TIMING_COUNTERPART) even for a
    plain "how's my career looking" question — this locks in that the
    template path now actually surfaces that already-computed data instead
    of stopping at the bare mood-word verdict."""
    from app.services.interpretation.templates import _topic_timing_hint

    context = {
        "career_timing_windows": [
            {
                "start_date": "2031-05-04", "end_date": "2033-11-21", "reason": "irrelevant here",
                "antardasha_lord_name": "Mercury", "transit_corroborated": False,
                "evidence_level": "house_lord_antardasha", "confidence": "strong",
                "literal_event_plausible": True,
            }
        ],
        "career_timing_direction": "future",
    }
    hint = _topic_timing_hint("career", context, hi=False)
    assert hint is not None
    assert "2031-05-04" in hint and "2033-11-21" in hint and "Mercury" in hint


def test_topic_timing_hint_is_none_without_a_timing_counterpart_or_windows():
    from app.services.interpretation.templates import _topic_timing_hint

    # "health" has no entry in _TOPIC_TIMING_COUNTERPART at all.
    assert _topic_timing_hint("health", {"health_timing_windows": [{"start_date": "x"}]}, hi=False) is None
    # "career" has a counterpart, but nothing was actually fetched this turn.
    assert _topic_timing_hint("career", {}, hi=False) is None


async def test_chat_reply_career_topic_answer_includes_the_real_timing_window_when_available():
    context = {**_CHAT_CONTEXT, "career_timing_windows": [
        {
            "start_date": "2031-05-04", "end_date": "2033-11-21", "reason": "irrelevant here",
            "antardasha_lord_name": "Mercury", "transit_corroborated": False,
            "evidence_level": "house_lord_antardasha", "confidence": "strong", "literal_event_plausible": True,
        }
    ], "career_timing_direction": "future"}
    reply = await interpreter.chat_reply(_history("How's my career looking this year?"), context, "en")
    # The generic "no strong push either way, so a lot depends on your own
    # effort and choices" reason is dropped once a real, specific timing
    # window is available right after it — caught live, it directly
    # contradicted the concrete window that followed it in the same reply.
    assert reply.startswith("Your career may have both good phases and hard phases.")
    assert "no strong push" not in reply
    assert "2031-05-04" in reply and "Mercury" in reply


async def test_chat_reply_answers_dosha_question_with_real_findings():
    reply = await interpreter.chat_reply(_history("Am I manglik?"), _CHAT_CONTEXT, "en")
    assert "Manglik" in reply
    assert "Gajakesari" not in reply  # yoga, not a dosha — must not bleed in


async def test_chat_reply_answers_dosha_question_with_none_found():
    context = {**_CHAT_CONTEXT, "yogas": []}
    reply = await interpreter.chat_reply(_history("Do I have any dosha?"), context, "en")
    assert "didn't find" in reply.lower()


async def test_chat_reply_dosha_question_includes_an_active_sade_sati_or_dhaiya():
    """Regression guard for a real bug caught live: "do I have any dosha"
    only ever checked the natal-only yogas list (Manglik/Kaal Sarp/
    Kemadruma) — a real, currently active Sade Sati or Dhaiya (both time-
    aware, computed in daily_reading's doshas list) was silently omitted
    even when genuinely active, so the exact same person could see "no
    dosha" from a direct dosha question while a life-theme question
    correctly surfaced their active Dhaiya."""
    context = {
        **_CHAT_CONTEXT,
        "yogas": [],  # no natal Manglik/Kaal Sarp/Kemadruma this time
        "daily_reading": {
            **_CHAT_CONTEXT["daily_reading"],
            "doshas": [
                {"key": "manglik", "label": "Manglik (Mangal Dosha)", "is_present": False},
                {"key": "kaal_sarp", "label": "Kaal Sarp Dosha", "is_present": False},
                {"key": "sade_sati", "label": "Sade Sati (setting)", "is_present": False},
                {"key": "dhaiya", "label": "Dhaiya", "is_present": True},
                {"key": "kemadruma", "label": "Kemadruma Dosha", "is_present": False},
            ],
        },
    }
    reply = await interpreter.chat_reply(_history("Do I have any dosha?"), context, "en")
    assert "Dhaiya" in reply
    assert "currently active" in reply.lower()


async def test_chat_reply_answers_yoga_question_with_real_findings():
    reply = await interpreter.chat_reply(_history("Do I have any yoga in my chart?"), _CHAT_CONTEXT, "en")
    assert "Gajakesari" in reply
    assert "Manglik" not in reply  # dosha, not a yoga


async def test_chat_reply_answers_life_theme_question_from_precomputed_context():
    # chat.py resolves the target date + calls prediction_service.get_life_theme
    # BEFORE calling chat_reply — this locks in that chat_reply correctly
    # surfaces whatever real theme text it was given for a resolvable past
    # question, without re-deriving anything itself.
    context = {
        **_CHAT_CONTEXT,
        "birth_year": 1990,
        "life_theme": {"theme": "You were running your Saturn Mahadasha then — a grinding, disciplined period.", "rating": 5},
    }
    reply = await interpreter.chat_reply(_history("What happened to me in 2016?"), context, "en")
    assert "Saturn Mahadasha" in reply


async def test_chat_reply_does_not_answer_life_theme_when_date_unresolvable():
    context = {**_CHAT_CONTEXT, "birth_year": 1990}  # no life_theme data attached — chat.py never fetched it
    reply = await interpreter.chat_reply(_history("Why did things feel so hard for me?"), context, "en")
    assert "Saturn Mahadasha" not in reply


async def test_chat_reply_surfaces_past_event_candidate_as_a_question_not_a_fact():
    """Regression guard for a real, reproduced bug: Product spec §13's Past
    Event Mode (chat.py's _recent_past_candidate) was fully implemented on
    the data-collection side but the rendering side was only ever written
    for the old LLM-based openai_interpreter.py — this native, no-LLM path
    (the primary one now) silently never turned that candidate into any
    visible text, so an open-ended past question fell all the way through
    to the generic Lagna-intro fallback instead of Product spec §13's
    "did something happen around [dates]?" question."""
    context = {
        **_CHAT_CONTEXT, "birth_year": 1990,
        "past_event_candidate": {
            "domains": ["career"], "start_date": "2016-01-01", "end_date": "2017-06-01",
            "reason": "irrelevant internal reasoning", "confidence": "medium",
        },
    }
    reply = await interpreter.chat_reply(_history("What important happened in my past?"), context, "en")
    assert "2016-01-01" in reply and "2017-06-01" in reply
    assert "career" in reply
    assert "don't want to guess" in reply.lower()


def test_decision_signal_recognizes_common_hinglish_leave_job_for_business_phrasing():
    """Regression guard for a real, reproduced bug: "Kya mujhe job chhodkar
    business karna chahiye?" (a very common Hinglish decision-question
    construction) matched neither the pure-English keywords (which require
    "my job") nor the pure-Hindi ones (which require "naukri") — it fell
    through to a plain career+money answer instead of gating on the
    decision-critical questions DECISION_SLOTS asks before advising."""
    from app.services.interpretation.templates import _detect_categories

    categories = _detect_categories("kya mujhe job chhodkar business karna chahiye")
    assert "job_change_decision" in categories


def test_decision_signal_recognizes_what_is_best_for_me_phrasing():
    """Regression guard for a real, reproduced bug: "What is best for me —
    stay on job or switch to business?" has no "should i" anywhere, so
    _has_decision_signal missed it entirely and this fell through to a
    plain career reading (Venus dasha dates) instead of the job_change_
    decision reason/offer/runway gate — even though the message already
    names both sides of the comparison."""
    from app.services.interpretation.templates import _detect_categories

    categories = _detect_categories("what is best for me stay on job or switch to business?")
    assert "job_change_decision" in categories


def test_past_tense_recognizes_pichle_without_an_adjacent_kya_hua_phrase():
    """Regression guard for a real, reproduced bug: "pichle kuch saalon mein
    kya important hua" (in the past few years, what important happened) has
    "kya" and "hua" separated by another word, so the existing "kya hua"
    phrase keyword never matched, and "pichle" (past/previous) wasn't
    recognized as a signal on its own."""
    assert message_mentions_past_tense("meri life mein pichle kuch saalon mein kya important hua")


async def test_chat_reply_word_boundary_matching_avoids_substring_false_positives():
    """Regression guard: bare "ill" (health keyword) is a substring of the
    extremely common word "will" ("when WILL I get married"), and bare "kid"
    (children keyword) is a substring of "kidney"/"kidding" — plain substring
    matching caught both live before word-boundary matching was added."""
    context1 = {**_CHAT_CONTEXT, "house_verdict": {**_CHAT_CONTEXT["house_verdict"], 6: "Health house text."}}
    reply = await interpreter.chat_reply(_history("When will I get a promotion?"), context1, "en")
    assert "Health house text." not in reply

    context = {**_CHAT_CONTEXT, "house_verdict": {**_CHAT_CONTEXT["house_verdict"], 5: "Children house text."}}
    reply2 = await interpreter.chat_reply(_history("My kidney has been hurting lately"), context, "en")
    assert "Children house text." not in reply2


def test_new_faq_keywords_do_not_false_fire_on_unrelated_words():
    """Regression guard for the government-job/PR/visa FAQ keyword expansion:
    short, real-world tokens like "PR" must only match as their own
    standalone word (word-boundary matched), never as a substring of an
    unrelated word (e.g. "pr" inside "surprise", "expression")."""
    assert not message_mentions_foreign_travel_timing("that was a nice surprise expression, when will I know?")
    assert message_mentions_foreign_travel_timing("when will I get my PR?")
    assert message_mentions_foreign_travel_timing("when will my visa come through?")


async def test_chat_reply_answers_dasha_question_naming_real_lords():
    reply = await interpreter.chat_reply(_history("What dasha am I running right now?"), _CHAT_CONTEXT, "en")
    assert "Jupiter" in reply and "Saturn" in reply


async def test_chat_reply_dasha_question_includes_the_real_effect_not_just_mechanism():
    """Regression guard: a raw "what dasha am I running" question used to
    only name WHICH planets are running (Mahadasha/Antardasha), with no
    effect at all — caught live from a real chat screenshot. The real,
    already-tested per-lord effect one-liner (_PERIOD_CONTENT, keyed by
    planet CODE, not the display name in mahadasha_lord/antardasha_lord)
    must now be appended."""
    context = {**_CHAT_CONTEXT, "antardasha_lord_code": "Sa"}
    reply = await interpreter.chat_reply(_history("What dasha am I running right now?"), context, "en")
    assert _PERIOD_CONTENT_EN["Sa"]["one_liner"] in reply


async def test_chat_reply_dasha_question_omits_effect_when_code_unavailable():
    # _CHAT_CONTEXT has no antardasha_lord_code — must not crash or fabricate.
    reply = await interpreter.chat_reply(_history("What dasha am I running right now?"), _CHAT_CONTEXT, "en")
    assert reply.strip().endswith("shaping this stretch of your life.")


async def test_chat_reply_answers_today_question_including_festival():
    reply = await interpreter.chat_reply(_history("What's today looking like for me?"), _CHAT_CONTEXT, "en")
    assert "unexpected change" in reply
    assert "Diwali" in reply


async def test_chat_reply_falls_back_to_chart_summary_when_nothing_matches():
    reply = await interpreter.chat_reply(_history("blah unrelated gibberish xyz"), _CHAT_CONTEXT, "en")
    assert "Sagittarius" in reply
    assert "career" in reply.lower()  # suggests real topics rather than a bare "please clarify"


async def test_chat_reply_handles_empty_history_without_crashing():
    reply = await interpreter.chat_reply([], _CHAT_CONTEXT, "en")
    assert "Sagittarius" in reply


# --- chat_reply: compound (multi-topic) questions ---------------------------
# "How's my career and marriage looking?" should answer BOTH real topics
# instead of only whichever one happened to be checked first — the old
# single-category if/elif chain could only ever return one.

async def test_chat_reply_answers_both_topics_in_a_compound_question():
    reply = await interpreter.chat_reply(
        _history("How's my career and marriage looking?"), _CHAT_CONTEXT, "en"
    )
    assert _CHAT_CONTEXT["house_verdict"][10] in reply
    assert _CHAT_CONTEXT["house_verdict"][7] in reply


async def test_chat_reply_caps_compound_questions_at_two_topics():
    # career + money + marriage all mentioned — only 2 of the 3 real answers
    # should come back, not an ever-growing wall of text.
    context = {
        **_CHAT_CONTEXT,
        "house_verdict": {**_CHAT_CONTEXT["house_verdict"], 2: "Venus sits here — this house governs money."},
    }
    reply = await interpreter.chat_reply(
        _history("How's my career, money, and marriage looking?"), context, "en"
    )
    matched = sum(
        text in reply
        for text in (context["house_verdict"][10], context["house_verdict"][2], context["house_verdict"][7])
    )
    assert matched == 2


# --- chat_reply: per-Rishi specialization -----------------------------------
# "Vasishtha only answers life direction, Parashara only timing, Gargi only
# relationships" — each Rishi answers questions in their own specialty from
# the same real facts as above, and redirects anything else to whichever
# Rishi actually owns it, instead of all five giving the same universal
# answer to every topic.

def _rishi_context(rishi_id: str) -> dict:
    return {**_CHAT_CONTEXT, "rishi_id": rishi_id}


async def test_bhrigu_answers_career_question_in_his_own_domain():
    # In-domain answers are prefixed with a rotating in-character lead-in
    # (see _pick_variant) rather than returned bare, so this checks
    # containment of the real fact, not an exact string match.
    reply = await interpreter.chat_reply(_history("How's my career looking?"), _rishi_context("bhrigu"), "en")
    assert _CHAT_CONTEXT["house_verdict"][10] in reply


async def test_bhrigu_still_answers_a_marriage_question_but_points_to_gargi():
    # Out-of-specialty no longer means a bare refusal — the user still gets
    # the real, chart-grounded answer, just with a pointer to the specialist
    # for more depth.
    reply = await interpreter.chat_reply(_history("Tell me about my marriage prospects"), _rishi_context("bhrigu"), "en")
    assert _CHAT_CONTEXT["house_verdict"][7] in reply
    assert "Gargi" in reply
    assert reply != _CHAT_CONTEXT["house_verdict"][7]  # the pointer is appended, not silently dropped


async def test_gargi_answers_marriage_but_still_answers_career_with_a_pointer_to_bhrigu():
    in_domain = await interpreter.chat_reply(_history("Tell me about my marriage prospects"), _rishi_context("gargi"), "en")
    assert _CHAT_CONTEXT["house_verdict"][7] in in_domain

    out_of_domain = await interpreter.chat_reply(_history("How's my career looking?"), _rishi_context("gargi"), "en")
    assert _CHAT_CONTEXT["house_verdict"][10] in out_of_domain
    assert "Bhrigu" in out_of_domain


async def test_gargi_answers_both_topics_of_a_mixed_scope_compound_question():
    # Marriage (Gargi's own domain) and career (Bhrigu's) asked together —
    # both get real answers, with a single pointer to Bhrigu, not one
    # redirect per out-of-scope topic.
    reply = await interpreter.chat_reply(
        _history("How's my career and marriage looking?"), _rishi_context("gargi"), "en"
    )
    assert _CHAT_CONTEXT["house_verdict"][7] in reply
    assert _CHAT_CONTEXT["house_verdict"][10] in reply
    assert reply.count("Bhrigu") == 1


async def test_parashara_answers_dasha_but_still_answers_dosha_with_a_pointer_to_agastya():
    in_domain = await interpreter.chat_reply(
        _history("What dasha am I running right now?"), _rishi_context("parashara"), "en"
    )
    assert "Jupiter" in in_domain and "Saturn" in in_domain

    out_of_domain = await interpreter.chat_reply(_history("Am I manglik?"), _rishi_context("parashara"), "en")
    assert "Manglik" in out_of_domain  # the real dosha finding, not just a refusal
    assert "Agastya" in out_of_domain


async def test_agastya_answers_dosha_and_yoga_but_points_to_bhrigu_for_money():
    dosha_reply = await interpreter.chat_reply(_history("Am I manglik?"), _rishi_context("agastya"), "en")
    assert "Manglik" in dosha_reply

    yoga_reply = await interpreter.chat_reply(_history("Do I have any yoga in my chart?"), _rishi_context("agastya"), "en")
    assert "Gajakesari" in yoga_reply

    # _CHAT_CONTEXT's house_verdict fixture has no house 2 (money) entry —
    # a real chart always would, but this exercises the "genuinely nothing to
    # answer with" fallback path: a pure pointer to Bhrigu, not a fabricated
    # answer.
    money_reply = await interpreter.chat_reply(_history("What about money?"), _rishi_context("agastya"), "en")
    assert "Bhrigu" in money_reply


async def test_vasishtha_answers_today_question_but_points_to_parashara():
    reply = await interpreter.chat_reply(_history("What's today looking like for me?"), _rishi_context("vasishtha"), "en")
    assert "Diwali" in reply  # real content from the daily reading, not withheld
    assert "Parashara" in reply


async def test_each_rishi_gives_a_distinct_specialized_fallback_when_nothing_matches():
    replies = {
        rishi_id: await interpreter.chat_reply(_history("blah unrelated gibberish xyz"), _rishi_context(rishi_id), "en")
        for rishi_id in ["vasishtha", "parashara", "gargi", "agastya", "bhrigu"]
    }
    # No longer the old universal "you can ask about career, marriage, money,
    # health..." string identical for every persona — five distinct replies.
    assert len(set(replies.values())) == 5


async def test_rishi_specialization_answers_in_hindi_too():
    reply = await interpreter.chat_reply(_history("मेरी शादी कैसी रहेगी?"), _rishi_context("gargi"), "hi")
    assert _CHAT_CONTEXT["house_verdict"][7] in reply


def _history_with_length(message: str, total_length: int) -> list[dict[str, str]]:
    filler = [{"role": "assistant", "content": "..."} for _ in range(total_length - 1)]
    return filler + [{"role": "user", "content": message}]


async def test_rishi_lead_in_and_fallback_rotate_instead_of_repeating():
    # "Talk like a real person, not the same repeated template" — the same
    # in-domain question asked at different points in a growing conversation
    # gets a different (hand-written) lead-in each time, while the
    # underlying real fact stays byte-for-byte identical.
    replies = [
        await interpreter.chat_reply(_history_with_length("How's my career looking?", n), _rishi_context("bhrigu"), "en")
        for n in (1, 2, 3)
    ]
    assert len(set(replies)) == 3
    for reply in replies:
        assert _CHAT_CONTEXT["house_verdict"][10] in reply

    # Same rotation applies to the "nothing matched" fallback text.
    fallback_replies = [
        await interpreter.chat_reply(_history_with_length("blah unrelated gibberish xyz", n), _rishi_context("vasishtha"), "en")
        for n in (1, 2, 3)
    ]
    assert len(set(fallback_replies)) == 3

    redirect = await interpreter.chat_reply(_history("मेरा करियर कैसा रहेगा?"), _rishi_context("gargi"), "hi")
    assert _CHAT_CONTEXT["house_verdict"][10] in redirect
    assert "भृगु" in redirect
