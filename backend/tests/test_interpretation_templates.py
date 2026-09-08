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
    _ordinal,
    _strip_trailing_stop,
)

interpreter = TemplateInterpreter()


@pytest.mark.parametrize(
    "n,expected",
    [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (10, "10th"), (11, "11th"), (12, "12th"), (21, "21st")],
)
def test_ordinal_suffixes(n, expected):
    assert _ordinal(n) == expected


def test_strip_trailing_stop_removes_terminal_punctuation_only():
    assert _strip_trailing_stop("Something clear.") == "Something clear"
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
    "yogas": [
        {"key": "gajakesari", "name": "Gajakesari Yoga", "description": "Moon and Jupiter in mutual Kendra houses."},
        {"key": "manglik", "name": "Manglik (Mangal) Dosha", "description": "Mars sits in a Manglik-checked house."},
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
    assert reply == _CHAT_CONTEXT["house_breakdown"][10]


async def test_chat_reply_answers_marriage_question_from_real_house_seven_text():
    reply = await interpreter.chat_reply(_history("Tell me about my marriage prospects"), _CHAT_CONTEXT, "en")
    assert reply == _CHAT_CONTEXT["house_breakdown"][7]


async def test_chat_reply_answers_hindi_career_question():
    reply = await interpreter.chat_reply(_history("मेरा करियर कैसा रहेगा?"), _CHAT_CONTEXT, "hi")
    assert reply == _CHAT_CONTEXT["house_breakdown"][10]


async def test_chat_reply_answers_dosha_question_with_real_findings():
    reply = await interpreter.chat_reply(_history("Am I manglik?"), _CHAT_CONTEXT, "en")
    assert "Manglik" in reply
    assert "Gajakesari" not in reply  # yoga, not a dosha — must not bleed in


async def test_chat_reply_answers_dosha_question_with_none_found():
    context = {**_CHAT_CONTEXT, "yogas": []}
    reply = await interpreter.chat_reply(_history("Do I have any dosha?"), context, "en")
    assert "didn't find" in reply.lower()


async def test_chat_reply_answers_yoga_question_with_real_findings():
    reply = await interpreter.chat_reply(_history("Do I have any yoga in my chart?"), _CHAT_CONTEXT, "en")
    assert "Gajakesari" in reply
    assert "Manglik" not in reply  # dosha, not a yoga


async def test_chat_reply_answers_dasha_question_naming_real_lords():
    reply = await interpreter.chat_reply(_history("What dasha am I running right now?"), _CHAT_CONTEXT, "en")
    assert "Jupiter" in reply and "Saturn" in reply


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
