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
from app.services.life_context_service import VALID_DOMAINS

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


# --- D. Priority-ordered GPT context assembly (pure, no provider call) -----

def build_priority_context(message: str, focus: dict, facts: dict, prior_questions_text: str = "") -> str:
    """Assembles the plain-language text every GPT call in this module
    receives, in strict priority order: current message > conversation focus
    (app.services.conversation_state.get_focus) > intent-relevant facts.
    `facts` is expected to already be question_strategy.usable_facts()'s OWN
    output — the existing category-relevance filter that already excludes an
    unrelated topic's facts outright (e.g. an old relationship-conflict
    thread when the current message is about career) — this function does
    NOT re-filter, only assembles in priority order. Cross-user
    QuestionPatternStats patterns are deliberately never included here —
    advisory-only inclusion happens separately inside
    assess_and_generate_question's own prompt, never anything the
    interpretation layer sees."""
    lines = [f"Current message: {message}"]
    if focus.get("topic"):
        sub = f" ({focus['sub_intent']})" if focus.get("sub_intent") else ""
        lines.append(f"Current topic/intent: {focus['topic']}{sub}")
    if focus.get("active_decision"):
        lines.append(f"Active decision: {focus['active_decision']}")
    if focus.get("known_for_decision"):
        known = "; ".join(f"{k}={v}" for k, v in focus["known_for_decision"].items() if v)
        if known:
            lines.append(f"Already known for this decision: {known}")
    if focus.get("missing_for_decision"):
        lines.append(f"Still missing for this decision: {', '.join(focus['missing_for_decision'])}")
    for domain, keys in (facts or {}).items():
        for key, info in keys.items():
            value = info.get("value") if isinstance(info, dict) else info
            if value:
                lines.append(f"{domain}.{key}: {value}")
    if prior_questions_text:
        lines.append(f"Previously asked this user: {prior_questions_text}")
    return "\n".join(lines)


# --- E. Answer-sufficiency gate + GPT-generated questions -------------------

_TARGET_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_ASSESS_SYSTEM_PROMPT = (
    "You are the information-discovery layer of an astrology-chat app. You are given the user's "
    "COMPLETE relevant context (current message, conversation focus, and known facts, already "
    "filtered to what's relevant — never invent or assume anything beyond it), the active decision "
    "category, and a short summary of what this user was previously asked. Decide TWO things "
    "together: (1) answer-sufficiency — a 0-100 confidence score for whether there is enough "
    "information to answer the CURRENT question well (this is NOT astrology confidence and is "
    "never shown to the user); (2) if not sufficient, ONE single follow-up question to ask next. "
    "You may propose a genuinely new information requirement beyond an existing fixed question "
    "catalogue when none of them fit, but target_domain MUST be exactly one of: "
    + ", ".join(sorted(VALID_DOMAINS)) + " — pick the closest bucket, never invent a new one. "
    "target_key must be a short snake_case identifier for the SPECIFIC missing fact (e.g. "
    "\"weekly_hours\", \"existing_customers\") reusing an existing name where an equivalent concept "
    "was already asked about this user. Never include any astrology content (no planets, houses, "
    "dasha, predictions) — you are gathering information, not answering. Never ask about something "
    "already listed as known. If a special case is flagged (a 'changed my plan' retraction with a "
    "named active_decision), ask a confirmation question naming that specific prior decision instead "
    "of a generic one, and set is_confirmation true. Return only JSON matching: "
    "{\"answer_ready\": bool, \"confidence\": int (0-100), \"missing_information\": [string, ...], "
    "\"next_question_required\": bool, \"question\": string or null, \"target_domain\": string or "
    "null, \"target_key\": string or null, \"is_confirmation\": bool}."
)


def _valid_assessment(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("answer_ready"), bool) or not isinstance(data.get("next_question_required"), bool):
        return False
    confidence = data.get("confidence")
    if not isinstance(confidence, int) or not (0 <= confidence <= 100):
        return False
    if not isinstance(data.get("missing_information"), list) or not all(isinstance(m, str) for m in data["missing_information"]):
        return False
    if not data.get("next_question_required"):
        return True
    question, domain, key = data.get("question"), data.get("target_domain"), data.get("target_key")
    if not isinstance(question, str) or not question.strip():
        return False
    if domain not in VALID_DOMAINS:
        return False
    if not isinstance(key, str) or not _TARGET_KEY_RE.match(key):
        return False
    return True


async def assess_and_generate_question(
    category: str, complete_context_text: str, prior_questions_text: str, message: str,
    conversation_snippet: str, language: str,
) -> dict | None:
    """Part of the explicitly opted-into "dynamic questioning" product
    decision (chat_dynamic_questions_enabled) — replaces the earlier, more
    constrained choose_next_slot (which could only pick among candidates
    conversation_engine.questions_for() had already computed). This can
    additionally propose a genuinely new information requirement, bounded to
    VALID_DOMAINS with a sanitized target_key, and returns an
    answer-sufficiency verdict alongside it so both decisions come from one
    round-trip and stay consistent with each other.

    `next_question_required=True` can only ever ask for MORE than the
    deterministic system's own required-fact checks — the caller
    (app.api.v1.chat) never lets this WAIVE a fact conversation_engine.
    known_slot treats as mandatory; it only ever adds to it. Fails closed to
    None (caller falls back to the deterministic questions_for() question/
    gate already computed) on any invalid field, timeout, disagreement, or
    error — same contract every function in this module uses."""
    settings = get_settings()
    if not settings.chat_dynamic_questions_enabled or not settings.openai_api_key or not message.strip():
        return None
    from openai import AsyncOpenAI
    try:
        async with AsyncOpenAI(
            api_key=settings.openai_api_key, max_retries=0,
            timeout=settings.chat_gpt_mediator_timeout_seconds,
        ) as client:
            response = await asyncio.wait_for(client.chat.completions.create(
                model=settings.openai_model, max_tokens=300,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _ASSESS_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({
                        "category": category,
                        "context": complete_context_text,
                        "prior_questions": prior_questions_text,
                        "message": message,
                        "conversation_snippet": conversation_snippet,
                        "language": language,
                    })},
                ],
            ), timeout=settings.chat_gpt_mediator_timeout_seconds)
        data = json.loads(response.choices[0].message.content)
        if not _valid_assessment(data):
            return None
        return data
    except Exception:
        return None


# --- E. Unknown-message intent rescue (classification only, never an answer) --

# The exact category strings the deterministic engine already knows how to
# handle (DECISION_SLOTS / native_understanding.detect_intents /
# templates._detect_categories) — kept short and curated on purpose. GPT
# picks ONE of these, or "none"; it can never invent a category the rest of
# the pipeline wouldn't recognize. Extend this list only when a new engine
# category is added elsewhere, never as a one-off patch for a single phrase
# (that's what native_understanding.py's own patterns are for).
_KNOWN_CATEGORIES = (
    "career", "career_confusion", "career_promotion_timing", "job_change_decision",
    "business", "business_start_decision",
    "marriage", "marriage_timing", "relationship_conflict", "spouse_relationship", "family_planning",
    "money", "wealth_timing", "debt", "financial_stability", "investment_decision",
    "family", "children", "siblings", "friends",
    "relocation_decision", "house_purchase_decision", "property_sale_intent",
    "week_ahead", "year_ahead", "travel", "foreign_travel_timing",
)

_INTENT_RESCUE_SYSTEM_PROMPT = (
    "You classify a short astrology-chat message into EXACTLY ONE of a fixed list of category "
    "IDs — you are not answering the message, only picking the closest matching category, so "
    "never include astrology content, advice, or a greeting in your response. You are given the "
    "conversation's previously active category (may be null) and the user's new message. If the "
    "message continues the previous topic (e.g. asking for a solution, changing a stated plan, a "
    "short follow-up with no topic word of its own), pick whichever category best fits that "
    "CONTINUED topic. If the message clearly starts a different topic, pick whichever category "
    "matches THAT instead. If truly nothing fits, return \"none\". Return only JSON matching "
    "{\"category\": \"...\"}, where the value is EXACTLY one of: " + ", ".join((*_KNOWN_CATEGORIES, "none"))
)


async def classify_unmapped_intent(message: str, previous_categories: list[str], language: str) -> str | None:
    """Last-resort rescue for a message native_understanding.detect_intents
    and conversation_engine's topic-continuation heuristics both found
    NOTHING for (see app.api.v1.chat) — called only once every deterministic
    path has already failed, never in place of them or before them. GPT
    picks from the FIXED _KNOWN_CATEGORIES list above; a returned value
    outside that list (or "none", or any error/timeout) is treated exactly
    like a failure — the caller falls back to the existing generic "what do
    you want to talk about" question, never guesses further. Classification
    only: GPT never sees astrology content and never writes the actual
    answer — the rescued category still goes through the full deterministic
    engine, identically to a category native_understanding found on its
    own."""
    settings = get_settings()
    if not settings.chat_gpt_mediator_enabled or not settings.openai_api_key or not message.strip():
        return None
    from openai import AsyncOpenAI
    try:
        async with AsyncOpenAI(
            api_key=settings.openai_api_key, max_retries=0,
            timeout=settings.chat_gpt_mediator_timeout_seconds,
        ) as client:
            response = await asyncio.wait_for(client.chat.completions.create(
                model=settings.openai_model, max_tokens=30,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _INTENT_RESCUE_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({
                        "previous_category": previous_categories[0] if previous_categories else None,
                        "message": message, "language": language,
                    })},
                ],
            ), timeout=settings.chat_gpt_mediator_timeout_seconds)
        category = json.loads(response.choices[0].message.content).get("category")
        return category if category in _KNOWN_CATEGORIES else None
    except Exception:
        return None


# --- F. Genuinely unanswerable fallback (direct GPT reply, no astrology) ---

_UNANSWERABLE_SYSTEM_PROMPT = (
    "You are a short, warm conversational fallback for an astrology-chat app, used ONLY after the "
    "app's own engine and its category classifier both found nothing that matches the user's message. "
    "Reply in the SAME language and script the message is written in (English, Hindi, or Hindi written "
    "in Latin script). Use simple, everyday words. You have NO chart data and MUST NOT make any "
    "astrological claim, prediction, or mention of planets, houses, dasha, or timing — never invent "
    "one. If the message is a normal conversational remark, respond warmly and briefly like a person "
    "would. If it seems to need real chart-based insight, say honestly that you'd need to know more, "
    "and suggest naming a specific area — career, relationships, money, or family. Keep it to 1-3 "
    "short sentences. Return only JSON matching {\"reply\": \"...\"}."
)


async def answer_unmapped(message: str, language: str) -> str | None:
    """Last resort AFTER classify_unmapped_intent has ALSO failed to place
    the message into any known category (see app.api.v1.chat) — at this
    point the deterministic engine genuinely has nothing to offer, and the
    only alternative left is the fully generic "what do you want to talk
    about" question forever. This lets GPT give a short, honest, plain-
    language reply instead — explicitly forbidden from inventing any
    astrological content, so it can only ever be conversational filler or
    an honest "tell me more," never a fabricated chart claim. Whatever the
    user stated in their own message is still captured as a fact the
    normal way: native_understanding.extract_knowledge already runs on
    every message regardless of category and persists via the same
    upsert_fact path — this function does not need its own storage step."""
    settings = get_settings()
    if not settings.chat_gpt_mediator_enabled or not settings.openai_api_key or not message.strip():
        return None
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
                    {"role": "system", "content": _UNANSWERABLE_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"message": message, "language": language})},
                ],
            ), timeout=settings.chat_gpt_mediator_timeout_seconds)
        reply = json.loads(response.choices[0].message.content).get("reply")
        if not isinstance(reply, str) or not reply.strip():
            return None
        # Fail closed: this function must never be the channel a fabricated
        # astrology claim slips through — same forbidden-term check as a
        # last-line defense on top of the system prompt's own instruction.
        if re.search(r"\b(?:planet|planets|house|houses|dasha|nakshatra|yoga|transit|retrograde)\b", reply.lower()):
            return None
        return reply
    except Exception:
        return None


# --- G. Final GPT interpretation layer (reconstructs, never paraphrases) ---

# Internal terminology the interpretation layer must never surface to the
# user — a rewrite that leaks any of these is discarded outright, regardless
# of how natural the rest of it reads.
_INTERNAL_TERM_RE = re.compile(
    r"\b(?:confidence score|slot[_ ]?id|target_domain|target_key|answer_ready|"
    r"missing_information|decision_slots?|dynamicquestionlog|questionpatternstats)\b", re.IGNORECASE,
)

_INTERPRETATION_SYSTEM_PROMPT = (
    "You are the final interpretation layer of a personal astrology-chat app — a real astrologer "
    "explaining a chart, not a system pasting outputs together. You are given: the user's actual "
    "current question, their conversation focus, relevant saved context about their life, a "
    "STRUCTURED result the astrology engine already computed, a list of specific facts that MUST "
    "appear in your answer, and a fallback answer already written by the deterministic engine (for "
    "reference only — do not imitate its sentence structure, ordering, or filler phrasing).\n\n"
    "THE ENGINE DETERMINES WHAT IS TRUE. YOU DETERMINE HOW TO EXPLAIN IT. Never calculate, invent, "
    "modify, or contradict an astrological fact — never change a date, a planet, a verdict, or add a "
    "timing window, placement, or event the structured result doesn't contain. Every fact in "
    "facts_to_preserve must appear in substance (not the same words, the same MEANING).\n\n"
    "SUCCESS CRITERION: the user must understand what the engine's result means SPECIFICALLY for "
    "their question. Good grammar or a warmer tone is not success if the answer doesn't actually "
    "explain the signal. For every important engine signal (a verdict, a window, a planetary "
    "period), translate it into what it MEANS, not just what it IS — 'financial_signal=positive' "
    "becomes something like 'this points to a period where improving your financial position is "
    "supported', not 'this is good for your money'. A date window becomes what that window is FOR "
    "and why it matters, not just the two dates. Do not overload the user with house numbers, "
    "planet names, lordships, nakshatras, dignity, yoga names, or dasha terminology unless they "
    "explicitly asked which planet/house is responsible — translate the mechanism into its meaning "
    "instead (e.g. a period lord becomes 'a phase your chart associates with X', not 'Mercury "
    "Antardasha').\n\n"
    "ANSWER THE ACTUAL QUESTION, NOT AN ADJACENT ONE — identify which sub-intent the current message "
    "actually maps to and lead with that; only after that may you mention a closely related optional "
    "topic. Never concatenate engine templates end to end — reconstruct one coherent explanation. Use "
    "relevant saved context only when it genuinely improves this specific answer (a business owner's "
    "financial question can reference their business; don't invent context that isn't given, and "
    "don't force in a stored fact that isn't relevant here). Never repeat a fact already explained "
    "earlier in this conversation just because it's known. Ask a follow-up question only when it "
    "would genuinely add a useful next level of analysis — never a generic 'what do you want to talk "
    "about next?', and never automatically after every answer.\n\n"
    "REMOVE, do not merely reword, generic filler that doesn't convey real information: 'good times "
    "and tough times', 'no strong push either way', 'this period is a grind, not a disaster', 'at "
    "this stage, X questions often involve...', 'looking at your real chart...', 'based on what "
    "you've shared...'. If the engine genuinely has no meaningful signal for some part of the "
    "question, say so honestly in plain words — never manufacture a personalized-sounding sentence "
    "to fill the space.\n\n"
    "NEVER expose internal mechanics: no confidence scores, domain/key identifiers, \"slot\", "
    "\"template\", database-sounding field names, or any internal terminology. Keep the SAME "
    "language and script as the original (English, Hindi, or Hinglish) — never translate or switch. "
    "Before answering, check silently: did I answer the actual question, using the real engine "
    "result, in language a normal person understands with zero astrology background? If not, "
    "rewrite. Return only JSON matching {\"reply\": \"...\"}."
)


def _values_present(text: str, values: list[str]) -> bool:
    lowered = text.lower()
    return all(str(v).lower() in lowered for v in values if str(v).strip())


# compose_final_reply is explicitly allowed (and expected — see its own
# system prompt) to reformat an ISO date into natural language ("2027-03-18"
# -> "March 2027") for readability. A plain substring check would reject
# that as if it dropped the fact, and _NUMBER_RE's own date-agnostic
# tokenizing would ALSO flag "March" (a real word, not a number) or the
# date's own digit fragments as a "new, unexplained token" once reformatted
# — caught live: this genuinely rejected a correct, well-reworded reply.
_MONTH_NAMES_EN = (
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
)


def _date_components(date_str: str) -> set[str]:
    try:
        year, month, day = date_str.split("-")
    except ValueError:
        return set()
    return {year, month, day, month.lstrip("0") or "0", day.lstrip("0") or "0", _MONTH_NAMES_EN[int(month) - 1]}


def _date_expressed(date_str: str, text: str) -> bool:
    """A date survives if it appears verbatim, OR the same year and month
    are both expressed in the text somehow (digits or the month's name) —
    it just can't turn into a DIFFERENT date."""
    if date_str in text:
        return True
    try:
        year, month, _day = date_str.split("-")
    except ValueError:
        return False
    lowered = text.lower()
    month_name = _MONTH_NAMES_EN[int(month) - 1]
    return year in text and (month_name in lowered or month.lstrip("0") in text or month in text)


def build_facts_to_preserve(text: str) -> list[str]:
    """The list of facts compose_final_reply's caller (app.api.v1.chat)
    should pass as `facts_to_preserve` — full dates and names, plus any
    NUMBER that isn't just a date's own internal digit fragment. Caught
    live: passing raw _fact_tokens(text) directly included "03"/"05" as
    their OWN required facts (since _NUMBER_RE matches every digit run,
    including inside an already-captured "2027-03-18") — rejecting a
    reply that correctly reformatted the date to "March 2027" as if it had
    dropped a fact, when the actual date was fully preserved."""
    dates = set(_DATE_RE.findall(text))
    date_fragments: set[str] = set()
    for d in dates:
        date_fragments |= _date_components(d)
    numbers = {n for n in _NUMBER_RE.findall(text) if n not in date_fragments}
    names = set(_MIDSENTENCE_CAP_RE.findall(text))
    return sorted(dates | numbers | names)


def _interpretation_facts_preserved(reply: str, facts_to_preserve: list[str]) -> bool:
    for fact in facts_to_preserve:
        fact = str(fact).strip()
        if not fact:
            continue
        if _DATE_RE.fullmatch(fact):
            if not _date_expressed(fact, reply):
                return False
        elif fact.lower() not in reply.lower():
            return False
    return True


_JSON_CAPITALIZED_WORD_RE = re.compile(r"[A-Z][a-z]+")


def _interpretation_has_no_fabricated_facts(
    reply: str, deterministic_fallback_text: str, facts_to_preserve: list[str], source_text: str,
) -> bool:
    """`source_text` is everything real GPT was actually given (the
    structured engine result + relevant saved context, serialized) — a
    genuine, legitimate signal can live there without ever having made it
    into the deterministic template's own narrower rendering (e.g. the
    fallback text only mentions the FUTURE window's period lord, but the
    structured result also names the CURRENT period's lord — GPT correctly
    using that is a strictly BETTER answer, not fabrication). Only a token
    traceable to NEITHER the fallback text, facts_to_preserve, NOR this
    source data counts as invented.

    Names in `source_text` are matched with a plain capitalized-word scan,
    not _fact_tokens' own prose-oriented _MIDSENTENCE_CAP_RE — that pattern
    requires a preceding "letter/comma + space" to avoid flagging a
    sentence's own first word, but `source_text` is serialized JSON, where a
    real value like "Venus" always sits right after a quote character
    (`"Venus"`), never after a natural-language word boundary — so the
    prose heuristic silently found nothing there at all."""
    allowed = (
        {str(f) for f in facts_to_preserve}
        | _fact_tokens(deterministic_fallback_text)
        | set(_DATE_RE.findall(source_text)) | set(_NUMBER_RE.findall(source_text))
        | set(_JSON_CAPITALIZED_WORD_RE.findall(source_text))
    )
    for date_str in (
        _DATE_RE.findall(deterministic_fallback_text) + _DATE_RE.findall(source_text)
        + [f for f in facts_to_preserve if _DATE_RE.fullmatch(str(f))]
    ):
        allowed |= _date_components(date_str)
    allowed_lower = {a.lower() for a in allowed}
    for token in _fact_tokens(reply):
        if token in allowed or token.lower() in allowed_lower:
            continue
        return False
    return True


async def compose_final_reply(
    user_message: str, focus_state: dict, relevant_context_text: str, structured_result: dict,
    facts_to_preserve: list[str], deterministic_fallback_text: str, language: str,
) -> str:
    """The mandatory-when-enabled final interpretation layer — a distinct,
    stricter capability from the disabled chat_gpt_mediator.beautify_reply
    (which only checked date/number/name token survival against the
    deterministic TEXT and could silently drop other content). This
    validates at the FACT level against `facts_to_preserve` and
    `structured_result`, never the sentence level, and is explicitly allowed
    to fully restructure the reply rather than paraphrase
    deterministic_fallback_text's own wording/ordering.

    Always returns a usable string: deterministic_fallback_text unchanged on
    any disabled/no-key/invalid/fabricated-content/timeout/error condition,
    so the app is always fully correct with this layer off, failing, or
    disabled — same fail-closed contract every function in this module uses."""
    settings = get_settings()
    if not settings.chat_interpretation_layer_enabled or not settings.openai_api_key or not deterministic_fallback_text.strip():
        return deterministic_fallback_text
    from openai import AsyncOpenAI
    try:
        async with AsyncOpenAI(
            api_key=settings.openai_api_key, max_retries=0,
            timeout=settings.chat_gpt_mediator_timeout_seconds,
        ) as client:
            response = await asyncio.wait_for(client.chat.completions.create(
                model=settings.openai_model, max_tokens=500,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _INTERPRETATION_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({
                        "user_message": user_message,
                        "focus": focus_state,
                        "context": relevant_context_text,
                        "structured_result": structured_result,
                        "facts_to_preserve": facts_to_preserve,
                        "fallback_answer": deterministic_fallback_text,
                        "language": language,
                    }, default=str)},
                ],
            ), timeout=settings.chat_gpt_mediator_timeout_seconds)
        reply = json.loads(response.choices[0].message.content).get("reply")
        if not isinstance(reply, str) or not reply.strip():
            return deterministic_fallback_text
        # Fail closed: every required fact must survive IN SUBSTANCE (a date
        # may be reformatted, e.g. "2027-03-18" -> "March 2027", but must
        # stay the SAME date — see _date_expressed), no internal term may
        # leak, and no NEW fact (date/number/name) beyond what the fallback
        # already carries may appear — this is what stops fabrication while
        # still allowing a fully reworded reply.
        if not _interpretation_facts_preserved(reply, facts_to_preserve):
            return deterministic_fallback_text
        if _INTERNAL_TERM_RE.search(reply):
            return deterministic_fallback_text
        source_text = relevant_context_text + " " + json.dumps(structured_result, default=str)
        if not _interpretation_has_no_fabricated_facts(reply, deterministic_fallback_text, facts_to_preserve, source_text):
            return deterministic_fallback_text
        return reply
    except Exception:
        return deterministic_fallback_text
