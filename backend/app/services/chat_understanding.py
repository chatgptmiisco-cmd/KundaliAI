"""Shared intent/memory contracts and native conversation understanding.

Provider credentials never change classification or structured memory.
Astrological answers remain in the existing calculation/interpretation engine.
"""
from dataclasses import dataclass, field

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
    "memory_recall": ("identity", "career", "business", "money", "relationships", "family", "goals", "preferences"),
    "business": ("business", "career", "money", "goals"),
    "investment_decision": ("money", "goals", "family"),
    "career": ("career", "business", "goals"),
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
    "job_change_decision": ("career", "business", "money", "family", "goals"),
    "business_start_decision": ("business", "money", "family", "goals"),
    "relocation_decision": ("career", "family", "relationships", "goals", "preferences"),
    "house_purchase_decision": ("money", "family", "goals", "preferences"),
    "marriage_decision": ("relationships", "family", "goals"),
    "property_sale_intent": ("money", "family", "preferences"),
    "property_inheritance_intent": ("family", "money", "preferences"),
    "property_relocation_intent": ("family", "preferences", "goals"),
    # Conversation Intelligence Layer sub-intents (native_understanding.py's
    # _SUB_INTENT_PATTERNS) — caught before being surfaced: a pure sub-intent
    # match with no co-occurring base category (e.g. "spouse_relationship"
    # detected alone, not alongside "marriage") had NO entry here at all, so
    # relevant_domains() returned nothing and native_response.py's
    # _context_lead_in/personal_context silently lost spouse-name/planning
    # facts even though life_state (checked independently) still worked.
    "spouse_relationship": ("relationships", "family"),
    "relationship_conflict": ("relationships", "family"),
    "family_planning": ("family", "relationships"),
    "workplace_problem": ("career", "business", "goals"),
    "career_confusion": ("career", "business", "goals"),
    "debt": ("money", "goals"),
    "financial_stability": ("money", "goals"),
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


async def classify_message(
    history: list[dict[str, str]], rishi_id: str | None, birth_year: int | None,
    language: str, open_decisions: list[dict] | None = None,
    pending_outcome_checkins: list[dict] | None = None,
    pending_reconfirmation: dict | None = None,
    decision_known_facts: dict[str, dict] | None = None,
    current_life_state: dict | None = None,
    pending_prediction_feedback: dict | None = None,
    pending_important_date: dict | None = None,
) -> ChatUnderstanding:
    """Always native: credentials never change memory or intent semantics."""
    from app.services.native_understanding import understand
    return understand(history, birth_year, language, open_decisions,
                      pending_outcome_checkins, pending_reconfirmation,
                      current_life_state, pending_prediction_feedback, pending_important_date)


async def extract_onboarding_context(topic: str, qa_pairs: list[tuple[str, str]]) -> list[ContextUpdate]:
    """Use the same explicit assertion parser for onboarding and chat."""
    from app.services.native_understanding import extract_knowledge
    facts = {}
    for question, answer in qa_pairs:
        updates, _, _, _ = extract_knowledge(answer)
        for update in updates:
            facts[update.domain, update.key] = update
        # A bounded answer to an explicit onboarding question is structured
        # knowledge too, even when it is not a full first-person sentence.
        from app.services.native_understanding import onboarding_slot
        slot = onboarding_slot(topic, question)
        if slot and answer.strip() and not updates:
            domain, key = slot
            facts[domain, key] = ContextUpdate(domain, key, answer.strip()[:240], "high", "user_stated")
    return list(facts.values())

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
