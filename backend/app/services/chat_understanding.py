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
from dataclasses import dataclass, field

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
_DECISION_CATEGORIES = (
    "job_change_decision", "business_start_decision", "relocation_decision",
    "house_purchase_decision", "marriage_decision",
    # Phase 9 — verdict-shaped like the decisions above (reuse the same
    # current/next-window framing), but NOT tracked as a LifeDecision (see
    # chat.py) — these are timing-support questions, not a "should I..."
    # choice the outcome-follow-up convention fits.
    "property_sale_intent", "property_inheritance_intent", "property_relocation_intent",
)
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
    "relocation_decision": "SHOULD they relocate/move abroad now (decision, not timing)",
    "house_purchase_decision": "SHOULD they buy a house now (decision, not timing)",
    "marriage_decision": "SHOULD they get married/commit now (decision, not timing, and NOT about a "
    "specific partner's compatibility)",
    "property_sale_intent": "WHETHER now is a supportive period for SELLING a property (not buying)",
    "property_inheritance_intent": "WHETHER now is a period of INHERITANCE-related property activation",
    "property_relocation_intent": "WHETHER now is a supportive period for CHANGING RESIDENCE/moving homes "
    "(not moving countries — that's a different category)",
    "dasha": "which planetary period they're currently running", "dosha": "doshas e.g. Manglik/Kaal Sarp/Sade Sati",
    "yoga": "classical yogas e.g. Raj Yoga", "today": "how today specifically looks",
    "year_ahead": "how this year overall looks",
    "life_theme": "what a specific past period/date was like, OR a genuinely open-ended reflection "
    "on the past with no specific date given at all (e.g. \"what happened in my past\", \"tell me "
    "something important about my history\") — this is NOT too vague to classify, it's its own "
    "real category; don't route it to needs_clarification",
}

# Which Life Context domains (see life_context_service.VALID_DOMAINS) are
# worth retrieving for a given detected category — deliberately scoped, not
# "always fetch everything": a plain career question doesn't need the
# user's family situation, but a job-change DECISION genuinely might (see
# the product spec's "retrieve only relevant context" / "does this
# materially change the answer" principles). Categories absent here (pure
# astrology ones: dasha/dosha/yoga/today/year_ahead/life_theme, plus
# education/health with no dedicated domain yet) retrieve nothing.
_CATEGORY_DOMAINS: dict[str, tuple[str, ...]] = {
    "career": ("career", "goals"),
    "career_timing": ("career", "goals"),
    "career_promotion_timing": ("career", "goals"),
    "money": ("money", "goals"),
    "wealth_timing": ("money", "goals"),
    "marriage": ("relationships", "family"),
    "marriage_timing": ("relationships", "family"),
    "family": ("family", "relationships"),
    "children": ("family", "relationships"),
    "children_timing": ("family", "relationships"),
    "siblings": ("family",),
    "friends": ("relationships",),
    "travel": ("preferences", "goals"),
    "foreign_travel_timing": ("preferences", "goals"),
    "business_expansion_timing": ("business", "money", "goals"),
    "business_partnership_timing": ("business", "relationships"),
    # Decisions genuinely need the wider picture — this is what lets a
    # "should I leave my job" answer account for a planned child or a
    # spouse's view without the user re-explaining it every time.
    "job_change_decision": ("career", "money", "family", "relationships", "goals"),
    "business_start_decision": ("business", "money", "family", "goals"),
    "relocation_decision": ("career", "family", "relationships", "goals", "preferences"),
    "house_purchase_decision": ("money", "family", "goals", "preferences"),
    "marriage_decision": ("relationships", "family", "goals"),
    "property_sale_intent": ("money", "family", "preferences"),
    "property_inheritance_intent": ("family", "money", "preferences"),
    "property_relocation_intent": ("family", "preferences", "goals"),
}


def relevant_domains(categories: list[str]) -> list[str]:
    seen: list[str] = []
    for category in categories:
        for d in _CATEGORY_DOMAINS.get(category, ()):
            if d not in seen:
                seen.append(d)
    return seen


@dataclass
class ContextUpdate:
    domain: str  # career | business | money | relationships | family | goals | preferences | identity
    key: str  # short, reusable, e.g. "occupation", "employer", "main_concern", "top_goal"
    value: str
    confidence: str  # high | medium | low
    source: str  # user_stated | inferred — never "user_confirmed" from this path, see chat_understanding docstring


@dataclass
class EventUpdate:
    event_type: str  # new_job | promotion | started_business | marriage | breakup | moved_city | became_parent | other
    description: str
    year: int
    month: int | None = None


@dataclass
class DecisionUpdate:
    category: str  # job_change_decision | business_start_decision — which open decision this resolves
    status: str  # decided | abandoned
    final_choice: str | None = None


@dataclass
class LifeStateUpdate:
    """A deterministic life fact the Prediction Engine itself gates
    predictions on (see app.db.models.life_state.LifeState /
    app.services.prediction_service's already_married/already_has_children/
    business_state checks) — distinct from ContextUpdate (free-form
    LifeContextItem facts, used only for LLM prose personalization). Every
    field optional: only the ones the user actually stated get set; chat.py
    merges just those into the existing LifeState via
    user_service.apply_life_state_updates, never a full replace."""
    marital_status: str | None = None  # single | dating | engaged | married | divorced | widowed
    marriage_date: str | None = None  # ISO date, only when a real date/month was stated
    children_count: int | None = None
    pregnancy_status: str | None = None  # none | expecting
    expected_delivery: str | None = None  # ISO date
    career_state: str | None = None  # employed | unemployed | student
    business_state: str | None = None  # none | running | considering
    # Phase 8 — property_purchase engine's life-state gate.
    housing_status: str | None = None  # renting | owns_property | living_with_parents | other
    planning_property_purchase: bool | None = None
    has_home_loan: bool | None = None


VALID_FEEDBACK_VERDICTS = {"correct", "partial", "incorrect", "not_sure"}


@dataclass
class PredictionFeedbackReport:
    verdict: str  # correct | partial | incorrect | not_sure
    detail: str | None = None  # what actually happened, only for correct/partial


@dataclass
class ImportantDateUpdate:
    """Phase 5 — unifies "important dates" and "goal target dates": a real
    future date the user cares about (a deadline, an exam, a savings goal's
    target), captured so important_date_service can check back on it once
    it passes (see app.db.models.important_date.ImportantDate)."""
    domain: str  # career | business | money | relationships | family | goals | preferences | identity
    description: str
    target_date: str  # ISO date, only when a real date/month was stated


@dataclass
class ChatUnderstanding:
    categories: list[str]
    needs_clarification: bool = False
    clarifying_question: str | None = None
    context_updates: list[ContextUpdate] = field(default_factory=list)
    events: list[EventUpdate] = field(default_factory=list)
    decision_update: DecisionUpdate | None = None
    # Set when this message is the user's answer to an outcome check-in
    # question chat.py asked (see life_context_service.
    # get_decisions_due_for_outcome_checkin) — the raw text is enough for
    # life_context_service.record_outcome; no further structuring needed.
    outcome_report: str | None = None
    # Product spec §7 — Decision-critical gap-filling: set instead of
    # answering when the user wants real advice on an open decision but one
    # fact that would materially change that advice isn't known yet (see
    # the known_facts passed per open decision below). Deliberately a
    # separate field from clarifying_question/needs_clarification — that
    # pair means "too vague to even classify"; this means "classified fine,
    # but not safe to advise on yet" — so chat.py can tell the two apart
    # even though both short-circuit the engine calls the same way.
    decision_gap_question: str | None = None
    # Set when this message is the user's answer to a Context Decay
    # reconfirmation question chat.py asked (see life_context_service.
    # get_facts_due_for_reconfirmation) confirming the fact is unchanged —
    # a changed value is NOT reported here, it just flows through
    # context_updates as normal so it correctly supersedes the old one.
    reconfirmed: bool = False
    # Product spec's core gap: deterministic-engine-gating life facts (see
    # LifeStateUpdate) — separate from context_updates because these don't
    # just personalize prose, they change WHICH prediction the engine
    # computes (see prediction_service's marriage/children/business
    # redirects). None of its fields set unless the user actually stated
    # that specific fact this turn.
    life_state_update: LifeStateUpdate | None = None
    # Product spec §15/§30 — Historical Validation/Prediction Feedback: set
    # when this message answers a pending PredictionFeedback question (see
    # prediction_feedback_service.get_pending_feedback) chat.py surfaced
    # earlier — the vague-past-event fallback's "did you change roles
    # around 2016-2017?" kind of question. `detail` is only meaningful for
    # correct/partial (what actually happened, in the user's words) and
    # becomes a real LifeEvent; never set for a message unrelated to the
    # pending question.
    prediction_feedback: PredictionFeedbackReport | None = None
    # Phase 5: a real future date the user just stated tied to a goal/
    # deadline — see ImportantDateUpdate. None unless the message actually
    # states one; most messages don't.
    important_date_update: ImportantDateUpdate | None = None
    # Set when this message answers a pending important-date check-in
    # chat.py surfaced (see important_date_service.get_newly_passed) —
    # the raw text of what happened, same "just the text, no further
    # structuring" convention as outcome_report above. Only meaningfully
    # set when a check-in is actually pending.
    important_date_outcome: str | None = None


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
    "An open-ended question about the past with no specific date given (\"what happened in my "
    "past\", \"tell me something important about my history\") is ALSO NOT vague in this sense — "
    "that's a real, answerable category (life_theme) on its own, not a sign more information is "
    "needed. Set categories=[\"life_theme\"] and needs_clarification=false for it.\n\n"
    "If the user states or clearly implies any real fact about their life worth remembering "
    "for future conversations, extract it into context_updates — one entry per distinct fact, "
    "each: {{\"domain\": one of career/business/money/relationships/family/goals/preferences/"
    "identity, \"key\": a short reusable snake_case name (e.g. \"occupation\", \"employer\", "
    "\"current_role_tenure\", \"main_concern\", \"top_goal\", \"relationship_status\", "
    "\"important_person:wife\", \"salary_range\"), \"value\": the fact itself (short, factual, "
    "third person, in English regardless of target language), \"confidence\": \"high\" if "
    "directly stated, \"medium\"/\"low\" if you're reading between the lines, \"source\": "
    "\"user_stated\" if they said it outright, \"inferred\" if you're deducing it}}. "
    "Extract EVERY distinct fact the message contains — a single message routinely yields "
    "several (e.g. \"my wife thinks I shouldn't leave because we're planning a baby next "
    "year\" is at minimum relationship_status=married, important_person:wife's view on the "
    "decision, and a planned child next year). Never invent a detail beyond what's stated or "
    "reasonably implied, and never record your own advice or a question back to the user as "
    "if it were a fact about them. Leave context_updates=[] when the message has nothing new "
    "worth remembering (most short factual questions have nothing to extract).\n\n"
    "Separately, if the message describes something that actually HAPPENED at a real point in "
    "time (a new job, a promotion, starting a business, an engagement, marriage, a breakup, "
    "moving city, becoming a parent) — not a plan or a possibility, something that already "
    "occurred — add it to events: [{{\"event_type\": one of new_job/promotion/started_business/"
    "engagement/marriage/breakup/moved_city/became_parent/other, \"description\": short factual "
    "description, \"year\": int, "
    "\"month\": int 1-12 or null if unknown}}]. Only extract an event when a year is stated or "
    "clearly inferable (e.g. \"3 years ago\" from a message you know the date of) — never guess "
    "a year. Leave events=[] otherwise.\n\n"
    "Separately, if the message states a real FUTURE date tied to a goal or deadline they care "
    "about (an exam, a deadline, an anniversary, a savings target date — e.g. \"my exam is March "
    "5th\", \"I want to save $10k by December\", \"our anniversary is on the 12th next month\"), "
    "set important_date_update: {{\"domain\": one of career/business/money/relationships/family/"
    "goals/preferences/identity, \"description\": short factual description, \"target_date\": "
    "an ISO date (YYYY-MM-DD) resolved from what was said and the conversation's known dates — "
    "never a past date}}. Only set this for a genuinely concrete future date, never a vague "
    "timeframe (\"someday\", \"eventually\") — leave it null otherwise, which is most messages.\n\n"
    "{important_date_line}"
    "{prediction_feedback_line}"
    "{open_decisions_line}"
    "If the latest message states the user has actually made a final choice on one of those open "
    "decisions (not just leaning toward one — an actual done choice, e.g. \"I accepted the new "
    "job\", \"I decided to stay\", \"I'm not doing the startup after all\"), set decision_update: "
    "{{\"category\": the matching category from the open list, \"status\": \"decided\" if they "
    "went with an option or \"abandoned\" if they dropped the whole idea, \"final_choice\": short "
    "description of what they chose}}. Otherwise leave decision_update null — most messages "
    "(including ones that just discuss the decision further) don't resolve it.\n\n"
    "{decision_known_facts_line}"
    "DECISION-CRITICAL GAP CHECK — apply this whenever the LATEST message is asking for advice, a "
    "verdict, or real reasoning about job_change_decision, business_start_decision, relocation_"
    "decision, house_purchase_decision, or marriage_decision (whether or not it's already in the "
    "open-decisions list above — this applies the very first time the user ever raises it too, not "
    "only in a later conversation): before "
    "letting the answer proceed, check whether what's already known (see just above) states the ONE "
    "fact below for that category. If it's missing AND the current message doesn't already state it, "
    "you MUST set decision_gap_question to a short, warm question asking for exactly that fact instead "
    "of letting real advice be given without it — do not skip this check just because you could still "
    "say something generically useful without the fact.\n"
    "  - job_change_decision: normally, whether they already have another job offer lined up (or any "
    "concrete income plan) for after leaving. But if the message already frames this as choosing "
    "between two SPECIFIC named options (e.g. two named offers, \"job A vs job B\") rather than a "
    "general leave-or-stay question, that offer-exists question is trivially already answered by "
    "naming two of them — ask instead what actually differs between the two options (pay, growth, "
    "stability, location, or whatever they seem to care about) if that isn't stated yet.\n"
    "  - business_start_decision: how they would actually fund the business (savings, a loan, "
    "investors, keeping the job while building it, etc.).\n"
    "  - relocation_decision: whether this is primarily a job/work reason, a family reason, or a "
    "lifestyle choice, and whether they have a concrete place/timeline in mind.\n"
    "  - house_purchase_decision: normally, whether their financing/down payment is actually in "
    "place, or they're asking speculatively with no concrete plan yet. But if what's already known "
    "shows they already own property, ask instead whether they mean an additional/investment "
    "property or something else entirely — buying a first home and buying a second one are "
    "genuinely different questions, and the chart-based timing reasoning shouldn't proceed until "
    "that's clear.\n"
    "  - marriage_decision: whether they're asking about readiness in general, or about a "
    "relationship with a specific person already in mind (not which person — just whether one exists) "
    "— this shapes the answer's framing, since the chart can only speak to general timing/readiness, "
    "never a specific partner's compatibility.\n"
    "Before asking, actually read every value already listed above for that category (across every "
    "domain shown) — if ANY of them already semantically answers the fact, even if worded "
    "differently or filed under a key/domain you wouldn't have chosen yourself (e.g. a "
    "\"savings_duration\" or \"salary_range\" value can already answer the funding/income-plan "
    "question), that counts as already known: leave decision_gap_question null. Write "
    "decision_gap_question in {target_language_name}. The only reasons to leave it null: the fact is "
    "already known (per the check just above), the current message just answered it, or a close "
    "variant of this exact question already appears as an assistant turn earlier in this conversation "
    "(check history first — never ask it twice).\n\n"
    "{life_state_line}"
    "If the LATEST message directly states one of these deterministic life facts as CURRENTLY true "
    "(not a plan, not a possibility, not something you're inferring) — their marital_status (single/"
    "dating/engaged/married/divorced/widowed), an actual marriage_date, children_count, "
    "pregnancy_status (none/expecting), expected_delivery date, career_state (employed/unemployed/"
    "student), business_state (none/running/considering), housing_status (renting/owns_property/"
    "living_with_parents/other), planning_property_purchase (true/false — actively planning to buy), "
    "or has_home_loan (true/false) — set life_state_update with ONLY the "
    "field(s) actually stated, e.g. {{\"marital_status\": \"married\"}}. Never set a field the "
    "message doesn't directly support, and never set one that already matches what's shown above as "
    "current — only report an actual CHANGE or a first-time statement. Most messages set no fields "
    "at all: leave life_state_update null (not an object with all-null fields) when nothing new is "
    "stated. This is separate from context_updates above — a life-state fact changes which real "
    "prediction the engine computes, so it must be reported here even if you also record it as a "
    "context_update for prose purposes.\n\n"
    "{outcome_checkin_line}"
    "{reconfirmation_line}"
    "Respond with ONLY JSON, no markdown fences: "
    '{{"categories": [string, ...], "needs_clarification": bool, '
    '"clarifying_question": string|null, "context_updates": [{{"domain": string, "key": '
    'string, "value": string, "confidence": string, "source": string}}, ...], "events": '
    '[{{"event_type": string, "description": string, "year": int, "month": int|null}}, ...], '
    '"decision_update": {{"category": string, "status": string, "final_choice": string}}|null, '
    '"decision_gap_question": string|null, '
    '"outcome_report": string|null, "reconfirmed": bool, '
    '"life_state_update": {{"marital_status": string, "marriage_date": string, "children_count": '
    'int, "pregnancy_status": string, "expected_delivery": string, "career_state": string, '
    '"business_state": string, "housing_status": string, "planning_property_purchase": bool, '
    '"has_home_loan": bool}}|null, '
    '"prediction_feedback": {{"verdict": string, "detail": string}}|null, '
    '"important_date_update": {{"domain": string, "description": string, "target_date": string}}'
    '|null, "important_date_outcome": string|null}}. '
    "Omit any life_state_update key that wasn't actually stated "
    "rather than filling it with a guessed value. "
    "clarifying_question and decision_gap_question must be written in {target_language_name}; "
    "every other field stays in English regardless of target language, since they're internal "
    "records, never shown to the user directly."
)

_TARGET_LANGUAGE_NAME = {
    "en": "English",
    "hi": "Hindi",
    "hinglish": "Hinglish (casual, code-switched Hindi-English written in Roman/Latin script, never Devanagari)",
}


async def classify_message(
    history: list[dict[str, str]],
    rishi_id: str | None,
    birth_year: int | None,
    language: str,
    open_decisions: list[dict] | None = None,
    pending_outcome_checkins: list[dict] | None = None,
    pending_reconfirmation: dict | None = None,
    decision_known_facts: dict[str, dict] | None = None,
    current_life_state: dict | None = None,
    pending_prediction_feedback: dict | None = None,
    pending_important_date: dict | None = None,
) -> ChatUnderstanding:
    message = history[-1]["content"] if history else ""
    settings = get_settings()
    if not (settings.use_ai_interpretation and settings.openai_api_key):
        return _fallback_understanding(message, birth_year)

    from openai import AsyncOpenAI  # local import: only needed on this path

    domain = (_RISHI_DOMAIN_HI if language == "hi" else _RISHI_DOMAIN_EN).get(rishi_id, "every real-life topic")
    topics = "\n".join(f"- {c}: {_CATEGORY_HINTS_EN[c]}" for c in _ALL_CATEGORIES)
    open_decisions_line = (
        f"The user currently has these decisions open (from earlier conversations): "
        f"{json.dumps(open_decisions, ensure_ascii=False)}.\n\n"
        if open_decisions
        else "The user has no open tracked decisions right now — decision_update must be null.\n\n"
    )
    # Product spec §7 — fed unconditionally for BOTH fixed decision
    # categories (see chat.py), independent of whether either is already
    # tracked as "open" above, so gap-filling works the very first time a
    # decision is raised too, not only on a later conversation about a
    # decision that got tracked earlier.
    decision_known_facts_line = (
        f"Here's what's already known about the user, relevant to each kind of decision, in case the "
        f"latest message is asking for advice on one: {json.dumps(decision_known_facts, ensure_ascii=False)}.\n\n"
        if decision_known_facts
        else ""
    )
    # chat.py surfaces an outcome check-in question itself (deterministic
    # Python text, not the model's own words) right before this call, so by
    # the time classify_message runs, that question is already the most
    # recent assistant turn in `history` — this line just tells the model
    # such a question may be sitting there and worth checking for.
    outcome_checkin_line = (
        f"You were recently asked (as the assistant) how one of these past decisions turned out: "
        f"{json.dumps(pending_outcome_checkins, ensure_ascii=False)}. If the LATEST user message "
        "is answering that — describing how it went, better/worse/similar to expected, or any "
        "real update on the outcome — set outcome_report to a short factual summary of what they "
        "said. If the latest message is unrelated (a new question, ignoring the check-in), leave "
        "outcome_report null.\n\n"
        if pending_outcome_checkins
        else "outcome_report must be null — no outcome check-in is currently pending.\n\n"
    )
    # Product spec §13 — Context Decay: chat.py surfaces the reconfirmation
    # question itself (deterministic text, see chat.py's
    # _build_reconfirm_question), so by the time this runs, it's already
    # the most recent assistant turn in `history` — same convention as
    # outcome_checkin_line above.
    reconfirmation_line = (
        f"You were recently asked (as the assistant) to reconfirm whether this previously-recorded "
        f"fact is still true: {json.dumps(pending_reconfirmation, ensure_ascii=False)}. If the "
        "LATEST user message confirms it's unchanged (a plain \"yes\"/\"still the same\"/similar, "
        "with no new value stated), set reconfirmed=true. If it says something changed and states "
        "the new value, leave reconfirmed=false and instead capture the update as a normal "
        "context_update using the SAME domain and key as the fact above, so it correctly supersedes "
        "the old value. If the latest message is unrelated to this check (a new question, ignoring "
        "it), leave reconfirmed=false.\n\n"
        if pending_reconfirmation
        else "reconfirmed must be false — no reconfirmation is currently pending.\n\n"
    )
    # Product spec §15/§30 — Historical Validation/Prediction Feedback:
    # chat.py surfaces the falsifiable past-event question itself
    # (generated by the interpreter, not this function), so by the time
    # this runs it's already the most recent assistant turn in `history` —
    # same convention as outcome_checkin_line/reconfirmation_line above.
    prediction_feedback_line = (
        f"PENDING VALIDATION CHECK — you (as the assistant) recently asked the user, as your most "
        f"recent turn, to confirm or deny something about their own past: "
        f"{json.dumps(pending_prediction_feedback, ensure_ascii=False)}. You MUST check whether the "
        "LATEST user message is answering that, even if it's ALSO answering something else or "
        "asking a new question at the same time (e.g. \"yes, I changed roles then, it was tough\" "
        "answers it even though it adds detail beyond a bare yes). Any confirmation, denial, "
        "correction, or \"not sure\" counts as answering it — set prediction_feedback: "
        "{\"verdict\": \"correct\" if they confirm it as-described, \"partial\" if some of it was "
        "right but the details differ, \"incorrect\" if it didn't happen, \"not_sure\" if they "
        "genuinely don't know, \"detail\": a short factual description of what ACTUALLY happened in "
        "their own words (only for correct/partial — null otherwise)}. Only leave "
        "prediction_feedback null if the latest message is genuinely unrelated to this check (a "
        "brand new question that doesn't touch it at all).\n\n"
        if pending_prediction_feedback
        else "prediction_feedback must be null — no prediction feedback is currently pending.\n\n"
    )
    # Product spec §9/§46/§47 — feeding what's already known prevents two
    # failure modes: re-asking for a fact already on record, and (the
    # interpreter's job downstream, not this function's) blindly answering
    # a question whose premise the known life-state contradicts — e.g.
    # "when will I get married" from someone already marked married.
    life_state_line = (
        f"Here's what's already on record about the user's current life state (only real, "
        f"user-confirmed facts, never guessed): {json.dumps(current_life_state, ensure_ascii=False)}. "
        "Only report life_state_update for a field that's missing here or that the message "
        "actively changes.\n\n"
        if current_life_state
        else "Nothing is on record yet for the user's life state (marital status, children, career, "
        "business) — report life_state_update for anything the message directly states.\n\n"
    )
    # Phase 5: chat.py surfaces the important-date check-in question itself
    # (deterministic text, see chat.py's _build_important_date_checkin_
    # question), same convention as outcome_checkin_line/reconfirmation_line
    # above — by the time this runs it's already the most recent assistant
    # turn in `history`.
    important_date_line = (
        f"You were recently asked (as the assistant) what happened with this date the user had "
        f"mentioned: {json.dumps(pending_important_date, ensure_ascii=False)}. If the LATEST user "
        "message answers that — describing what happened, even briefly — set important_date_outcome "
        "to a short factual summary in their own words. If the latest message is unrelated, leave "
        "important_date_outcome null.\n\n"
        if pending_important_date
        else "important_date_outcome must be null — no important-date check-in is currently pending.\n\n"
    )
    system = _SYSTEM_PROMPT_EN.format(
        topics=topics, domain=domain, target_language_name=_TARGET_LANGUAGE_NAME[language],
        open_decisions_line=open_decisions_line, outcome_checkin_line=outcome_checkin_line,
        reconfirmation_line=reconfirmation_line, decision_known_facts_line=decision_known_facts_line,
        life_state_line=life_state_line, prediction_feedback_line=prediction_feedback_line,
        important_date_line=important_date_line,
    )
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            # Raised from 300 — context_updates can legitimately hold
            # several entries for one rich message (see the multi-fact
            # example in the system prompt).
            max_tokens=500,
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
        context_updates = [
            ContextUpdate(
                domain=u.get("domain", "preferences"),
                key=u.get("key", ""),
                value=u.get("value", ""),
                confidence=u.get("confidence", "medium"),
                source=u.get("source", "inferred"),
            )
            for u in data.get("context_updates", [])
            if u.get("key") and u.get("value")
        ]
        events = [
            EventUpdate(
                event_type=e.get("event_type", "other"),
                description=e.get("description", ""),
                year=e["year"],
                month=e.get("month"),
            )
            for e in data.get("events", [])
            if e.get("description") and isinstance(e.get("year"), int)
        ]
        raw_decision_update = data.get("decision_update")
        decision_update = (
            DecisionUpdate(
                category=raw_decision_update.get("category", ""),
                status=raw_decision_update.get("status", "decided"),
                final_choice=raw_decision_update.get("final_choice"),
            )
            if raw_decision_update and raw_decision_update.get("category")
            else None
        )
        raw_life_state_update = data.get("life_state_update")
        life_state_update = (
            LifeStateUpdate(
                marital_status=raw_life_state_update.get("marital_status"),
                marriage_date=raw_life_state_update.get("marriage_date"),
                children_count=raw_life_state_update.get("children_count"),
                pregnancy_status=raw_life_state_update.get("pregnancy_status"),
                expected_delivery=raw_life_state_update.get("expected_delivery"),
                career_state=raw_life_state_update.get("career_state"),
                business_state=raw_life_state_update.get("business_state"),
                housing_status=raw_life_state_update.get("housing_status"),
                planning_property_purchase=raw_life_state_update.get("planning_property_purchase"),
                has_home_loan=raw_life_state_update.get("has_home_loan"),
            )
            if raw_life_state_update
            else None
        )
        raw_prediction_feedback = data.get("prediction_feedback")
        prediction_feedback = (
            PredictionFeedbackReport(
                verdict=raw_prediction_feedback.get("verdict", "not_sure"),
                detail=raw_prediction_feedback.get("detail"),
            )
            if raw_prediction_feedback and raw_prediction_feedback.get("verdict") in VALID_FEEDBACK_VERDICTS
            else None
        )
        raw_important_date_update = data.get("important_date_update")
        important_date_update = (
            ImportantDateUpdate(
                domain=raw_important_date_update.get("domain", "goals"),
                description=raw_important_date_update.get("description", ""),
                target_date=raw_important_date_update.get("target_date", ""),
            )
            if raw_important_date_update
            and raw_important_date_update.get("description") and raw_important_date_update.get("target_date")
            else None
        )
        return ChatUnderstanding(
            categories=categories,
            needs_clarification=needs_clarification,
            clarifying_question=data.get("clarifying_question"),
            context_updates=context_updates,
            events=events,
            decision_update=decision_update,
            outcome_report=data.get("outcome_report"),
            decision_gap_question=data.get("decision_gap_question"),
            reconfirmed=bool(data.get("reconfirmed")),
            life_state_update=life_state_update,
            prediction_feedback=prediction_feedback,
            important_date_update=important_date_update,
            important_date_outcome=data.get("important_date_outcome"),
        )
    except Exception:
        _logger.warning("openai_classify_message_failed_falling_back_to_keywords", exc_info=True)
        return _fallback_understanding(message, birth_year)


_ONBOARDING_SYSTEM_PROMPT = (
    "A new user just signed up for a Vedic astrology app and picked \"{topic}\" as what they'd most "
    "like clarity about, then answered a short series of follow-up questions. Extract every real "
    "fact about their life from their answers into context_updates — one entry per distinct fact: "
    "{{\"domain\": one of career/business/money/relationships/family/goals/preferences/identity, "
    "\"key\": a short reusable snake_case name (e.g. \"occupation\", \"employer\", "
    "\"current_role_tenure\", \"main_concern\", \"top_goal\", \"relationship_status\"), \"value\": "
    "the fact itself (short, factual, third person, in English), \"confidence\": \"high\" if directly "
    "stated else \"medium\"/\"low\", \"source\": \"user_stated\" if said outright else \"inferred\"}}. "
    "Extract every distinct fact each answer contains, not just one per question. Never invent a "
    "detail beyond what's stated or reasonably implied.\n\n"
    "Respond with ONLY JSON, no markdown fences: "
    '{{"context_updates": [{{"domain": string, "key": string, "value": string, "confidence": string, '
    '"source": string}}, ...]}}.'
)


async def extract_onboarding_context(topic: str, qa_pairs: list[tuple[str, str]]) -> list[ContextUpdate]:
    """Product spec §1-2 — the short post-signup topic pick + 2-4 follow-up
    questions. Deliberately a separate, simpler extraction call from
    classify_message's (no category classification, no clarification, no
    events/decisions — those need a real chat conversation to make sense
    of): this is a one-shot "here's everything the user just told us,
    structure it" pass over a small fixed batch of answers, not an
    ongoing per-message pipeline."""
    settings = get_settings()
    if not (settings.use_ai_interpretation and settings.openai_api_key) or not qa_pairs:
        return []

    from openai import AsyncOpenAI  # local import: only needed on this path

    system = _ONBOARDING_SYSTEM_PROMPT.format(topic=topic)
    transcript = "\n".join(f"Q: {q}\nA: {a}" for q, a in qa_pairs)
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=500,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": transcript}],
        )
        data = json.loads(response.choices[0].message.content)
        return [
            ContextUpdate(
                domain=u.get("domain", "preferences"),
                key=u.get("key", ""),
                value=u.get("value", ""),
                confidence=u.get("confidence", "medium"),
                source=u.get("source", "inferred"),
            )
            for u in data.get("context_updates", [])
            if u.get("key") and u.get("value")
        ]
    except Exception:
        _logger.warning("openai_extract_onboarding_context_failed", exc_info=True)
        return []


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
