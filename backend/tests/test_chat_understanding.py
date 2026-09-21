"""Coverage for app.services.chat_understanding — the classification step
that decides which real-life categories a chat message touches, before any
Prediction Engine call happens. The OpenAI-backed branch isn't exercised
here (it needs a real API key and costs money); these tests lock in the
fallback branch (used whenever OpenAI isn't configured — the state of this
whole test environment) and the deterministic rishi-redirect computation,
both pure/local and safe to test without any network call."""
from app.services.chat_understanding import (
    ChatUnderstanding,
    classify_message,
    compute_out_of_domain_redirects,
    relevant_domains,
)
from app.services.interpretation.templates import _detect_categories


def _history(message: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": message}]


async def test_classify_message_falls_back_to_keyword_detection_without_openai_configured():
    # No USE_AI_INTERPRETATION/OPENAI_API_KEY set in the test environment —
    # must match _detect_categories exactly, never ask a clarifying
    # question, never extract any context updates (that needs real language
    # understanding this fallback deliberately doesn't attempt).
    message = "How's my career looking?"
    understanding = await classify_message(_history(message), "bhrigu", 1995, "en")
    assert understanding.categories == _detect_categories(message.lower(), 1995)
    assert understanding.needs_clarification is False
    assert understanding.clarifying_question is None
    assert understanding.context_updates == []


def test_detect_categories_promotion_question_suppresses_the_generic_career_parent():
    # career_timing's own keyword list is deliberately broad and includes
    # "promotion" (see _TOPIC_KEYWORDS["career"] in templates.py), so before
    # the _SUB_INTENT_SUPPRESSES_PARENT fix this returned BOTH
    # career_timing and career_promotion_timing for the identical question
    # — on the deterministic (no-LLM) chat_reply path that meant the SAME
    # window got described twice: once as "a career or job change" and
    # once as "a promotion". A promotion-specific question should surface
    # only the more specific category.
    message = "when will I get a promotion?"
    categories = _detect_categories(message, 1995)
    assert categories == ["career_promotion_timing"]


def test_detect_categories_plain_career_question_still_returns_career_timing():
    message = "when will I change my job?"
    categories = _detect_categories(message, 1995)
    assert categories == ["career_timing"]


async def test_classify_message_fallback_handles_empty_history():
    understanding = await classify_message([], "vyasa", None, "en")
    assert understanding == ChatUnderstanding(categories=[])


def test_compute_out_of_domain_redirects_empty_for_generalist_vyasa():
    # Vyasa has no entry in _RISHI_SPECIALTY, so nothing is ever "outside"
    # its domain — it answers every category directly.
    assert compute_out_of_domain_redirects(["marriage", "career"], "vyasa", "en") == {}


def test_compute_out_of_domain_redirects_empty_when_everything_is_in_domain():
    assert compute_out_of_domain_redirects(["career", "money"], "bhrigu", "en") == {}


def test_compute_out_of_domain_redirects_flags_categories_outside_specialty():
    result = compute_out_of_domain_redirects(["career", "marriage"], "bhrigu", "en")
    assert result == {"marriage": "Gargi"}


def test_compute_out_of_domain_redirects_handles_compound_question_two_owners():
    # career (Bhrigu's own domain) + marriage (Gargi) + health (Agastya)
    # asked of Bhrigu — only the two genuinely out-of-domain ones are
    # flagged, each to their real owner.
    result = compute_out_of_domain_redirects(["career", "marriage", "health"], "bhrigu", "en")
    assert result == {"marriage": "Gargi", "health": "Agastya"}


def test_compute_out_of_domain_redirects_uses_hindi_names_for_hindi_language():
    result = compute_out_of_domain_redirects(["marriage"], "bhrigu", "hi")
    assert result == {"marriage": "गार्गी"}


def test_relevant_domains_deduplicates_across_categories():
    result = relevant_domains(["career", "money"])
    assert result == ["career", "goals", "money"]


def test_relevant_domains_empty_for_pure_astrology_categories():
    assert relevant_domains(["dasha", "today"]) == []


def test_relevant_domains_wide_for_decision_categories():
    result = relevant_domains(["job_change_decision"])
    assert set(result) == {"career", "money", "family", "relationships", "goals"}


def test_relevant_domains_wide_for_relocation_decision():
    result = relevant_domains(["relocation_decision"])
    assert set(result) == {"career", "family", "relationships", "goals", "preferences"}
