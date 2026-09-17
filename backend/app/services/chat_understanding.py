"""Decides which of the chat pipeline's fixed real-life categories a message
is actually asking about — either via a small OpenAI classification call
(when configured) or by falling back to the existing deterministic keyword
matcher (`_detect_categories`) when it isn't. Either way, the actual answer
always comes from the real Prediction Engine (app.services.prediction_service
etc.) afterward — this module only decides WHERE to look, never what the
answer is.

Which categories a message touches is independent of which rishi is being
asked — staying out-of-scope/in-scope for a given rishi is a plain,
deterministic Python lookup (see compute_out_of_domain_redirects below),
never something the LLM decides.
"""
import json
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.interpretation.templates import (
    _CATEGORY_RISHI,
    _RISHI_DOMAIN_EN,
    _RISHI_DOMAIN_HI,
    _RISHI_NAME_EN,
    _RISHI_NAME_HI,
    _RISHI_SPECIALTY,
    _TIMING_CATEGORIES,
    _TOPIC_HOUSE,
    _detect_categories,
)

_logger = get_logger("chat_understanding")

# The full fixed vocabulary the classifier may choose from — same categories
# _detect_categories already knows, so the LLM and the regex fallback are
# always classifying into the same space the rest of the pipeline expects.
_DECISION_CATEGORIES = ("job_change_decision", "business_start_decision")
_OTHER_CATEGORIES = ("dasha", "dosha", "yoga", "today", "year_ahead", "life_theme")
_ALL_CATEGORIES: tuple[str, ...] = (
    tuple(_TOPIC_HOUSE) + tuple(_TIMING_CATEGORIES) + _DECISION_CATEGORIES + _OTHER_CATEGORIES
)

_CATEGORY_HINTS_EN = {
    "career": "career in general (not timing)", "money": "money/finances in general (not timing)",
    "marriage": "marriage/relationships in general (not timing)", "health": "health in general",
    "family": "family life", "education": "studies/exams", "friends": "friendships",
    "travel": "travel/relocation in general (not timing)", "children": "children in general (not timing)",
    "siblings": "siblings",
    "marriage_timing": "WHEN marriage will happen", "career_timing": "WHEN career will improve",
    "wealth_timing": "WHEN income will improve", "children_timing": "WHEN having children",
    "foreign_travel_timing": "WHEN foreign travel opportunities peak",
    "career_promotion_timing": "WHEN a promotion is likely", "business_expansion_timing": "WHEN to expand a business",
    "business_partnership_timing": "WHEN to take a business partner",
    "job_change_decision": "SHOULD they switch jobs now (decision, not timing)",
    "business_start_decision": "SHOULD they start a business now (decision, not timing)",
    "dasha": "which planetary period they're currently running", "dosha": "doshas e.g. Manglik/Kaal Sarp/Sade Sati",
    "yoga": "classical yogas e.g. Raj Yoga", "today": "how today specifically looks",
    "year_ahead": "how this year overall looks", "life_theme": "what a specific past period/date was like",
}


@dataclass
class ChatUnderstanding:
    categories: list[str]
    needs_clarification: bool = False
    clarifying_question: str | None = None
    user_note: str | None = None


def _fallback_understanding(message: str, birth_year: int | None) -> ChatUnderstanding:
    """No OpenAI configured — today's exact behavior, byte-for-byte: pure
    keyword detection, never asks a clarifying question, never extracts a
    memory note (that needs real language understanding to do safely)."""
    return ChatUnderstanding(categories=_detect_categories(message.lower(), birth_year))


_SYSTEM_PROMPT_EN = (
    "You classify a message sent to a Vedic astrology chat persona into a fixed set of "
    "real-life topics the app can actually compute answers for. Pick every topic the "
    "LATEST user message genuinely touches (usually 0-2) — do not restrict yourself to "
    "the persona's own specialty, detect every real topic present.\n\n"
    "Topics:\n{topics}\n\n"
    "This persona's own specialty is: {domain}. That's context only — still report every "
    "topic the message actually touches, even outside it.\n\n"
    "If the message is too vague to confidently pick any topic (e.g. \"I'm not feeling "
    "well these days\" could be health, family, career, or relationships), set "
    "needs_clarification=true and write ONE short clarifying question in the target "
    "language, phrased warmly like a caring person genuinely curious to help — not a form "
    "asking which category to file this under (avoid anything that reads like \"which area "
    "of your life...\"; prefer something like gently asking what's been going on) — do not "
    "guess and do not pick a topic in this case. If the user's latest message actually "
    "answers a clarifying question from earlier in the conversation, use the full "
    "conversation to now classify for real instead of asking again.\n\n"
    "Never ask a second clarifying question that is close in meaning to one you (or an "
    "earlier turn) already asked in this same conversation — check the recent assistant "
    "turns before writing one. If the user's answer to your first clarifying question is "
    "STILL vague, do not ask a third, narrower variant of the same question: instead commit "
    "to your single best-guess topic(s) from everything said so far (pick the closest "
    "matching topic rather than leaving categories empty) rather than stalling the "
    "conversation. When you do need to ask, vary the phrasing and angle from any earlier "
    "clarifying question in this conversation — never repeat the same sentence structure.\n\n"
    "A bare greeting with no real question at all (\"hi\", \"hello\", \"namaste\") is NOT "
    "vague in this sense — set categories=[] and needs_clarification=false for it rather "
    "than interrogating them about what they mean; a warm generic welcome is handled "
    "elsewhere for that case.\n\n"
    "If the user shares ANY personal detail worth remembering for future conversations — "
    "not just a mood, event, worry or plan, but also where they live, their job or field of "
    "work, relationship/family situation, or any other concrete fact about their life they "
    "volunteer — write ONE short factual third-person note capturing it in user_note (e.g. "
    "\"lives in Goverdhan\", \"works in IT\", \"feeling low lately, cause unclear\") for "
    "future personalization — otherwise leave user_note null. Never include advice or "
    "invented detail in it, and never fabricate a detail the user didn't actually state.\n\n"
    "Respond with ONLY JSON, no markdown fences: "
    '{{"categories": [string, ...], "needs_clarification": bool, '
    '"clarifying_question": string|null, "user_note": string|null}}. '
    "clarifying_question and user_note must be written in {target_language_name}."
)

_TARGET_LANGUAGE_NAME = {
    "en": "English",
    "hi": "Hindi",
    "hinglish": "Hinglish (casual, code-switched Hindi-English written in Roman/Latin script, never Devanagari)",
}


async def classify_message(
    history: list[dict[str, str]], rishi_id: str | None, birth_year: int | None, language: str
) -> ChatUnderstanding:
    message = history[-1]["content"] if history else ""
    settings = get_settings()
    if not (settings.use_ai_interpretation and settings.openai_api_key):
        return _fallback_understanding(message, birth_year)

    from openai import AsyncOpenAI  # local import: only needed on this path

    domain = (_RISHI_DOMAIN_HI if language == "hi" else _RISHI_DOMAIN_EN).get(rishi_id, "every real-life topic")
    topics = "\n".join(f"- {c}: {_CATEGORY_HINTS_EN[c]}" for c in _ALL_CATEGORIES)
    system = _SYSTEM_PROMPT_EN.format(
        topics=topics, domain=domain, target_language_name=_TARGET_LANGUAGE_NAME[language]
    )
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=300,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, *history[-10:]],
        )
        data = json.loads(response.choices[0].message.content)
        categories = [c for c in data.get("categories", []) if c in _ALL_CATEGORIES]
        needs_clarification = bool(data.get("needs_clarification")) and not categories
        if not categories and not needs_clarification:
            # The model found nothing AND didn't flag it as needing
            # clarification either — rather than let this fall all the way
            # through to an empty reply (which would otherwise resurface the
            # deterministic template's different voice as a last resort),
            # try the regex/fuzzy matcher too. It already handles typos well
            # ("carrer" -> career) that a single ambiguous short message can
            # trip up a small model on with no other context to lean on.
            categories = _detect_categories(message.lower(), birth_year)
        return ChatUnderstanding(
            categories=categories,
            needs_clarification=needs_clarification,
            clarifying_question=data.get("clarifying_question"),
            user_note=data.get("user_note"),
        )
    except Exception:
        _logger.warning("openai_classify_message_failed_falling_back_to_keywords", exc_info=True)
        return _fallback_understanding(message, birth_year)


def compute_out_of_domain_redirects(categories: list[str], rishi_id: str | None, language: str) -> dict[str, str]:
    """For a specialist rishi (one with an entry in _RISHI_SPECIALTY), maps
    each detected category outside their own domain to the display name of
    whichever rishi actually owns it — e.g. asking Bhrigu (career/money)
    about marriage returns {"marriage": "Gargi"}. Empty for the generalist
    Vyasa persona (absent from _RISHI_SPECIALTY, so it never has an
    "outside" domain) and for any category that's already in-domain."""
    if rishi_id not in _RISHI_SPECIALTY:
        return {}
    own_categories = _RISHI_SPECIALTY[rishi_id]
    rishi_names = _RISHI_NAME_HI if language == "hi" else _RISHI_NAME_EN
    return {
        category: rishi_names[_CATEGORY_RISHI[category]]
        for category in categories
        if category not in own_categories and category in _CATEGORY_RISHI
    }
