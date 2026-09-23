"""GPT Mediator Layer — a deliberately wider GPT role than chat_beautifier.py's
3-substitution allowlist, per explicit product decision: full free-form reply
paraphrase and pre-classification input cleanup, not just picking among 3
pre-reviewed connective phrases.

Both directions carry real, acknowledged residual risk that chat_beautifier.py's
narrow substitution mechanism structurally cannot: GPT is now producing genuine
free text, not choosing among fixed IDs. Each function below has its own
fail-closed safety check (polarity preservation for input, token preservation
for output), but neither check can catch every possible subtle meaning shift —
that's the tradeoff this mode was explicitly chosen for over the safer
alternative. When any check fails, or on any exception/timeout, always fall
back to the original, unedited text — same fail-closed contract
chat_beautifier.py already uses.

Stateless by design: every function here is given only the current turn's
text, nothing else. All conversation context and memory stays exactly where
it already lived — ConversationState (conversation_engine.py) and
LifeContextItem (life_context_service.py) — this module never remembers
anything itself, and never classifies or answers anything on its own.
"""
import asyncio
import json
import re

from app.core.config import get_settings

# --- A. Input normalization ------------------------------------------------

# Anchor words whose polarity (present vs. negated) must survive cleanup
# unchanged — the exact class of fact a "typo correction" could otherwise
# silently flip in a way that's catastrophic for this app specifically (an
# already-married user getting treated as single, or vice versa). Narrow and
# specific on purpose, not a general sentiment check — same curated,
# grow-over-time anchor-word philosophy already proven in
# native_understanding.py's own _FACT_ANCHOR_WORDS.
_POLARITY_ANCHORS = (
    "married", "single", "divorced", "engaged", "widowed", "unmarried",
    "pregnant", "employed", "unemployed", "shaadi", "शादीशुदा",
)
_NEGATORS = {"not", "no", "never", "nahi", "nahin", "नहीं"}


def _polarity_signature(text: str) -> set[tuple[str, bool]]:
    """(anchor, negated) pairs for every anchor word present — a coarse but
    cheap proxy for "did the stated meaning flip" between two versions of
    the same message. Two texts with the same signature may still differ in
    wording; that's fine, this only guards against the one failure mode
    that matters here."""
    text = text.lower()
    clauses = re.split(r"[.!?;\n]", text)
    signature: set[tuple[str, bool]] = set()
    for clause in clauses:
        words = [w.strip(".,!?") for w in clause.split()]
        negated = any(w in _NEGATORS for w in words)
        for anchor in _POLARITY_ANCHORS:
            if re.search(rf"\b{re.escape(anchor)}\b", clause):
                signature.add((anchor, negated))
    return signature


_INPUT_SYSTEM_PROMPT = (
    "You clean up spelling and grammar in a short astrology-chat message so a downstream "
    "deterministic engine can parse it. Fix only typos and garbled phrasing (e.g. \"elation "
    "ship\" -> \"relationship\"). Never add, remove, or reverse any stated fact: marital "
    "status, names, dates, numbers, and negation words (not/no/never/nahi) must stay exactly "
    "as meant in the original. Never translate or switch language/script — keep it in whatever "
    "language and script (English, Hindi, or Hinglish) the user actually typed in. Never answer "
    "the message yourself. If you are not confident about a cleanup, return the message "
    "unchanged. Return only JSON matching {\"cleaned\": \"...\"}."
)


async def normalize_input(message: str, language: str, engine_only: bool = False) -> str:
    """Runs BEFORE native classification (see app.api.v1.chat) — the cleaned
    text feeds detect_intents/extract_knowledge/resume(), but the ORIGINAL,
    unedited message is still what's stored in ChatMessage.content, so
    history and quote-backs stay honest to what the user actually typed."""
    settings = get_settings()
    if engine_only or not settings.chat_gpt_mediator_enabled or not settings.openai_api_key or not message.strip():
        return message
    from openai import AsyncOpenAI
    try:
        async with AsyncOpenAI(
            api_key=settings.openai_api_key, max_retries=0,
            timeout=settings.chat_gpt_mediator_timeout_seconds,
        ) as client:
            response = await asyncio.wait_for(client.chat.completions.create(
                model=settings.openai_model, max_tokens=150,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _INPUT_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"message": message, "language": language})},
                ],
            ), timeout=settings.chat_gpt_mediator_timeout_seconds)
        cleaned = json.loads(response.choices[0].message.content).get("cleaned")
        if not isinstance(cleaned, str) or not cleaned.strip():
            return message
        # Fail closed: any polarity drift discards the cleanup entirely,
        # regardless of how plausible the rest of the rewrite looks.
        if _polarity_signature(cleaned) != _polarity_signature(message):
            return message
        return cleaned
    except Exception:
        return message


# --- B. Full free-form reply paraphrase -------------------------------------

_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUMBER_RE = re.compile(r"\b\d[\d,]*\b")
# Capitalized words that aren't the first word of a sentence — a cheap proxy
# for a proper noun (spouse name, place) actually asserted in the reply, not
# just a sentence-initial capital that carries no fact of its own.
_MIDSENTENCE_CAP_RE = re.compile(r"(?<=[a-zA-Z,]\s)([A-Z][a-z]+)")


def _fact_tokens(text: str) -> set[str]:
    return set(_DATE_RE.findall(text)) | set(_NUMBER_RE.findall(text)) | set(_MIDSENTENCE_CAP_RE.findall(text))


_REPLY_SYSTEM_PROMPT = (
    "Rewrite the given astrology-chat answer to sound warm, natural, and human — like a real "
    "person explaining it, not a report. Use SIMPLE, everyday words a person with only basic "
    "English (or basic Hindi, matching whichever language the original is in) would easily "
    "understand — short sentences, no fancy vocabulary. You MUST NOT add, remove, or change any "
    "fact: every date, number, name, and verdict (favorable/unfavorable/mixed, or similar) must "
    "carry over exactly, in the same digit/date format, never spelled out or altered. Do not add "
    "any astrology term (house, planet, dasha, nakshatra, yoga) that is not already present in "
    "the original text. Do not add new claims, advice, or questions beyond what's already there. "
    "The \"language\" field tells you what language the original is in (en=English, hi=Hindi, "
    "hinglish=Hindi written in Latin script mixed with English words) — your rewrite MUST stay in "
    "that EXACT SAME language and script. Never translate or switch to a different language, even "
    "partially. Return only JSON matching {\"rewritten\": \"...\"}."
)


async def beautify_reply(native_reply: str, language: str) -> str:
    """Replaces chat_beautifier.beautify()'s 3-substitution mechanism when
    chat_gpt_mediator_enabled is on (see that flag's own docstring in
    app.core.config) — genuine free-form rewriting, not just picking among
    fixed phrase IDs. The token-preservation check below is real but
    partial: it guarantees no date/number/name silently vanishes, it cannot
    guarantee the surrounding meaning never shifts. That gap is the
    accepted tradeoff for allowing real rewriting at all."""
    settings = get_settings()
    if not settings.chat_gpt_mediator_enabled or not settings.openai_api_key or not native_reply.strip():
        return native_reply
    from openai import AsyncOpenAI
    try:
        async with AsyncOpenAI(
            api_key=settings.openai_api_key, max_retries=0,
            timeout=settings.chat_gpt_mediator_timeout_seconds,
        ) as client:
            response = await asyncio.wait_for(client.chat.completions.create(
                model=settings.openai_model, max_tokens=400,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _REPLY_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"answer": native_reply, "language": language})},
                ],
            ), timeout=settings.chat_gpt_mediator_timeout_seconds)
        rewritten = json.loads(response.choices[0].message.content).get("rewritten")
        if not isinstance(rewritten, str) or not rewritten.strip():
            return native_reply
        # Fail closed: every date/number/name token in the original must
        # survive verbatim in the rewrite, or the whole rewrite is discarded.
        if not _fact_tokens(native_reply) <= _fact_tokens(rewritten):
            return native_reply
        return rewritten
    except Exception:
        return native_reply


# --- C. Clarifying-question simplification (display-only) ------------------

_NUMBERED_LINE_RE = re.compile(r"^\s*\d+[.)]", re.MULTILINE)

_QUESTION_SYSTEM_PROMPT = (
    "Simplify the wording of this astrology-chat clarifying question so it reads more "
    "naturally, using SIMPLE, everyday words a person with only basic English (or basic Hindi, "
    "matching whichever language it's already in) would easily understand. Keep the SAME "
    "language and script it's already in — never translate or switch to a different one. If it "
    "has numbered options, you MUST keep exactly the same number of options, in the same order "
    "and meaning — only the phrasing may change. Never add or remove an option. Return only JSON "
    "matching {\"simplified\": \"...\"}."
)


async def simplify_question(question_text: str, language: str) -> str:
    """Display-only — safe by construction as long as the option count is
    preserved: conversation_engine.resume() binds a reply to a pending slot
    using stored slot IDs and numbered position, never by re-parsing this
    displayed text, so simplifying the wording here cannot corrupt the
    answer mapping (see conversation_engine.py's QUESTIONS/DECISION_SLOTS)."""
    settings = get_settings()
    if not settings.chat_gpt_mediator_enabled or not settings.openai_api_key or not question_text.strip():
        return question_text
    from openai import AsyncOpenAI
    try:
        async with AsyncOpenAI(
            api_key=settings.openai_api_key, max_retries=0,
            timeout=settings.chat_gpt_mediator_timeout_seconds,
        ) as client:
            response = await asyncio.wait_for(client.chat.completions.create(
                model=settings.openai_model, max_tokens=250,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _QUESTION_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"question": question_text, "language": language})},
                ],
            ), timeout=settings.chat_gpt_mediator_timeout_seconds)
        simplified = json.loads(response.choices[0].message.content).get("simplified")
        if not isinstance(simplified, str) or not simplified.strip():
            return question_text
        # Fail closed: option count must match exactly, or the simplification
        # is discarded — this is what keeps resume()'s positional slot
        # binding safe (see module docstring above).
        if len(_NUMBERED_LINE_RE.findall(simplified)) != len(_NUMBERED_LINE_RE.findall(question_text)):
            return question_text
        return simplified
    except Exception:
        return question_text
