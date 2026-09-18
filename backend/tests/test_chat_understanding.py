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
