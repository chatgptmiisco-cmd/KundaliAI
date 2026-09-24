"""Personalized interpretation of computed facts, before optional styling."""
import re

from app.services.interpretation.templates import TemplateInterpreter
from app.services.native_understanding import choose


# Categories whose _context_lead_in reframe (templates.py) already states
# marital status naturally in prose ("Since you're already married...") —
# personal_context's own "your relationship status: married" line right
# next to that is the exact "debugging statement, not a human response"
# repetition called out live. Suppressed only for THIS one fact, only for
# these categories — every other fact still surfaces normally, and a
# category with no reframe still gets the plain fact list.
_CATEGORIES_WITH_MARITAL_REFRAME = frozenset((
    "marriage", "marriage_timing", "spouse_relationship", "relationship_conflict", "family_planning",
))


def _has_marital_reframe(context) -> bool:
    return bool(
        (context.get("life_state") or {}).get("marital_status") == "married"
        and _CATEGORIES_WITH_MARITAL_REFRAME.intersection(context.get("detected_categories") or ())
    )


_RAW_TOKEN_RE = re.compile(r"^[a-z]+(?:_[a-z]+)+$")


def _humanize_raw_token(value: str) -> str:
    """Safety net for a real, reproduced leak: some facts are written as
    internal enum-style tokens for GATING purposes only (e.g. business.stage
    = "has_customers"/"early_revenue" — see native_understanding.
    extract_knowledge), never meant to be shown verbatim. A free-text value
    the user actually typed is a sentence with spaces, never a pure
    underscore-joined token, so this only ever fires on the internal-enum
    case — turns "has_customers" into "has customers" rather than leaking
    database-looking text into the reply."""
    return value.replace("_", " ") if _RAW_TOKEN_RE.match(value) else value


# Keys that only mean something in the context of ONE specific decision
# flow (both written exclusively by job_change_decision's own DECISION_
# SLOTS questions — see conversation_engine.QUESTIONS) — caught live: once
# stated, these kept echoing on EVERY later career-domain reply, including
# a plain bare "career" mention that had nothing to do with the earlier
# job-change conversation ("your reason for changing: stress; your
# alternative: I already have another offer" showing up on an unrelated
# "career" question days — or even one turn — later). A fact being
# recently stated (not yet stale) is a different thing from it being
# relevant to what's being asked RIGHT NOW; personal_context had no notion
# of the latter at all. Scoped to the one category they actually answer.
_DECISION_SCOPED_KEYS = {
    "change_reason": "job_change_decision",
    "alternative_opportunity": "job_change_decision",
}


def personal_context(context, language):
    facts = context.get("life_context", {})
    skip_relationship_status = _has_marital_reframe(context)
    active_categories = set(context.get("detected_categories") or ())
    pieces = []
    labels = {
        "occupation": ("your work", "आपका काम", "aapka kaam"),
        "industry": ("your field", "आपका क्षेत्र", "aapka field"),
        "transition_intent": ("your intended transition", "आपका बदलाव का इरादा", "aapka transition plan"),
        "business_type": ("your business idea", "आपका व्यवसाय विचार", "aapka business idea"),
        "stage": ("your business stage", "आपके व्यवसाय का चरण", "aapka business stage"),
        "savings": ("your financial buffer", "आपकी आर्थिक बचत", "aapki savings"),
        "financial_responsibilities": ("your commitments", "आपकी जिम्मेदारियां", "aapki zimmedariyan"),
        "top_goal": ("your goal", "आपका लक्ष्य", "aapka goal"),
        "change_reason": ("your reason for changing", "बदलाव की वजह", "badlav ki wajah"),
        "alternative_opportunity": ("your alternative", "आपका विकल्प", "aapka option"),
        "relationship_status": ("your relationship status", "आपकी रिश्ते की स्थिति", "aapka relationship status"),
        "children_count": ("your children", "आपके बच्चे", "aapke bachche"),
        "planning_intent": ("your family planning", "आपकी पारिवारिक योजना", "aapki family planning"),
        "spouse_name": ("your spouse", "आपके जीवनसाथी", "aapke spouse"),
    }
    seen = set()
    seen_labels = set()
    for domain, values in facts.items():
        for key, fact in values.items():
            # Rendered separately below from goal_history instead — a single
            # "top_goal" fact only ever shows the LATEST goal, losing earlier
            # ones the moment a new one supersedes it (Phase 7's correction
            # history preserves them; this just wasn't surfacing them).
            if domain == "goals" and key == "top_goal":
                continue
            if key == "relationship_status" and skip_relationship_status:
                continue
            required_category = _DECISION_SCOPED_KEYS.get(key)
            if required_category and required_category not in active_categories:
                continue
            value = str(fact["value"])
            # Captured lowercase like every other free-text extraction (see
            # native_understanding.py's extract_knowledge) — a proper noun
            # reads as personal, not as a data-entry glitch, when displayed.
            display_value = value.title() if key == "spouse_name" else _humanize_raw_token(value)
            if fact.get("source") not in ("user_stated", "user_confirmed") or fact.get("confidence") == "low" or value in seen:
                continue
            # Caught live, reproducing the exact leak this function exists to
            # prevent: DECISION_SLOTS writes free-text answers under internal
            # slot keys ("goal", "funding", "customer_supplier_contacts"...)
            # that were never given a friendly label below. The old fallback
            # rendered them anyway via `key.replace("_", " ")` — a literal
            # internal field name shown to the user ("goal: clothing and
            # yes i have customers,; funding: ..."), exactly what "never
            # expose field names" means. Those keys already get real
            # natural-language synthesis (_named_facts_sentence) — an
            # unlabeled key is skipped here rather than raw-dumped.
            if key not in labels:
                continue
            label = choose(language, *labels[key])
            # A single statement ("I want to switch to business") can write
            # the SAME key under two different domains with two slightly
            # different literal values (career.transition_intent="business",
            # business.transition_intent="start a business" — see
            # native_understanding.extract_knowledge) — caught live: this
            # rendered the identical label twice back to back ("your
            # intended transition: start a business; your intended
            # transition: business."). The value-only `seen` check above
            # doesn't catch it since the values differ; dedupe by label too.
            if label in seen_labels:
                continue
            seen.add(value)
            seen_labels.add(label)
            pieces.append(f"{label}: {display_value}")
    # Stage 2 — goals as a list: up to 3 most recent DISTINCT goals ever
    # stated (oldest-to-newest history, deduped case-insensitively), not
    # just whichever one happens to be active right now.
    recent_goals, seen_goals = [], set()
    for entry in reversed(context.get("goal_history") or []):
        text = str(entry["value"])
        if text.lower() in seen_goals:
            continue
        seen_goals.add(text.lower())
        recent_goals.append(text)
        if len(recent_goals) == 3:
            break
    if recent_goals:
        label = choose(language, "your goals" if len(recent_goals) > 1 else "your goal", "आपके लक्ष्य", "aapke goals")
        pieces.append(f"{label}: {'; '.join(recent_goals)}")
    if not pieces:
        return ""
    return choose(language, "From what you've shared, ", "आपने जो बताया है, उसके अनुसार — ", "Aapne jo bataya hai, uske mutabik — ") + "; ".join(pieces[:5]) + "."


_SELF_REFERENCE_PREFIX_RE = re.compile(
    r"^(?:yes,?\s+)?(?:i(?:'m| am)?\s+)?(?:already\s+)?(?:i\s+)?(?:have|has|had|got|want to|plan to|am)\s+",
    re.IGNORECASE,
)


def _as_clause(value: str) -> str:
    """A DECISION_SLOTS answer is free text the user typed in their own
    first-person voice ("I already have another offer") — interpolating it
    as-is into a sentence that supplies its OWN "you already have {value}"
    framing produces an awkward double self-reference ("you already have I
    already have another offer"). Strips a leading self-referential phrase
    so the value reads as a plain noun clause instead; falls back to the
    untouched original if nothing recognizable is found, so real content is
    never lost. Display-only — the stored fact value is never touched."""
    stripped = _SELF_REFERENCE_PREFIX_RE.sub("", value.strip(), count=1).strip()
    return stripped or value


def _named_facts_sentence(category, facts, language):
    """Turns the SPECIFIC facts conversation_engine's DECISION_SLOTS already
    collected for this category into one connected, forward-moving
    sentence — not a flat "your X is A; your Y is B" restatement (a real,
    reproduced complaint: repeating back what the user just said, with no
    synthesis, "doesn't add much"). Where a genuinely meaningful
    combination exists (e.g. a stated reason together with an offer in
    hand), draws the same kind of inference a person would, instead of
    just listing both. No astrology calculation changes: prediction_
    service's verdict is untouched, this only shapes the prose around it
    from values already sitting in context["life_context"]."""
    career, money, business, relationships = (
        facts.get(d, {}) for d in ("career", "money", "business", "relationships")
    )

    def val(bucket, key):
        value = bucket.get(key, {}).get("value")
        return _humanize_raw_token(value) if value else value

    if category == "job_change_decision":
        reason, offer, runway = val(career, "change_reason"), val(career, "alternative_opportunity"), val(money, "savings")
        if not any((reason, offer, runway)):
            return None
        has_offer = bool(offer) and not any(t in offer.lower() for t in ("no offer", "no job offer", "none", "नहीं"))
        offer_clause = _as_clause(offer) if offer and has_offer else offer
        if reason and offer:
            lead = choose(language,
                f"{reason.capitalize()} is what's driving this, and you already have {offer_clause} — so it's not "
                f"just about wanting out, there's something concrete pulling you too." if has_offer else
                f"{reason.capitalize()} is driving this, but {offer} — so the real question right now is timing "
                f"and readiness, not just whether to look.",
                f"{reason} ही असली वजह है, और आपके पास {offer_clause} भी है — यानी सिर्फ छोड़ने की बात नहीं, एक ठोस विकल्प भी है।"
                if has_offer else
                f"{reason} वजह है, लेकिन {offer} — इसलिए असली सवाल समय और तैयारी का है, सिर्फ तलाश का नहीं।")
        elif reason:
            lead = choose(language, f"{reason.capitalize()} is what's actually driving this.", f"{reason} ही असली वजह है।")
        elif offer:
            lead = choose(language, f"You mentioned: {offer}.", f"आपने बताया: {offer}।")
        else:
            lead = None
        if not runway:
            return lead
        tail = choose(language,
            f"With {runway} to fall back on, there's real room to plan this properly rather than rush it.",
            f"{runway} होने से इसे जल्दबाज़ी में नहीं, ठीक से योजना बनाकर करने की गुंजाइश है।")
        return f"{lead} {tail}" if lead else tail
    # "business" (bare, e.g. "I want to switch to business" mid a career
    # conversation) reuses business_start_decision's exact same DECISION_
    # SLOTS/goal/funding keys (see conversation_engine.DECISION_SLOTS'
    # "business" entry) but was never added here — caught live: personal_
    # context() had no friendly label for "goal"/"funding" either, so a
    # plain "business" turn fell all the way through to a raw internal-key
    # dump ("goal: clothing...; funding: ...") instead of this synthesized
    # sentence. Same facts, same synthesis, just the other category name.
    if category in ("business_start_decision", "business"):
        goal, funding = val(business, "goal"), val(business, "funding")
        if not any((goal, funding)):
            return None
        funding_clause = _as_clause(funding) if funding else funding
        if goal and funding:
            return choose(language,
                f"You're thinking {goal}, funded by {funding_clause} — that's the actual combination worth "
                f"weighing against the timing below, not a generic business question.",
                f"आप {goal} सोच रहे हैं, {funding_clause} के सहारे — नीचे के समय को इसी संयोजन के आधार पर देखना चाहिए, किसी "
                f"सामान्य व्यवसाय सवाल के आधार पर नहीं।")
        if goal:
            return choose(language, f"You're thinking: {goal}.", f"आप यह सोच रहे हैं: {goal}।")
        return choose(language, f"You mentioned funding this through {funding_clause}.", f"आपने बताया कि इसे {funding_clause} से फंड करेंगे।")
    if category == "marriage_decision":
        constraints = val(relationships, "marriage_constraints")
        if not constraints:
            return None
        return choose(language,
            f"You mentioned: {constraints} — that's worth weighing directly, alongside the timing, not instead of it.",
            f"आपने बताया: {constraints} — इसे समय के साथ-साथ सीधे तौर पर भी देखना ज़रूरी है, सिर्फ समय के आधार पर नहीं।")
    return None


def practical_framing(context, language):
    """Only ever surfaces a sentence built from what the person actually
    said (_named_facts_sentence) — never a fixed, decision-framework
    paragraph identical for every user asking about the same category. A
    "Compare staying, accepting a concrete offer, and resigning without
    one... A supportive chart window is not a job offer" disclaimer used to
    live here, one hardcoded paragraph per decision type, unconditionally,
    for every single reply — exactly the internal "decision-framework
    explanation" language a real astrologer wouldn't recite out loud.
    Removed per direct, explicit feedback; the actual substance (comparing
    options, the chart not replacing real-world information) belongs in
    conversation only when it's genuinely relevant to what THIS person
    described, which is what _named_facts_sentence already does."""
    categories = context.get("detected_categories", [])
    facts = context.get("life_context", {})
    return "\n\n".join(s for c in categories if (s := _named_facts_sentence(c, facts, language)))


async def compose(history, context, language):
    categories = context.get("detected_categories", [])
    render_context = dict(context)
    # Keep the existing specialized calculation-to-text paths. These aliases
    # reuse only computed house facts; they do not create new predictions.
    render_context["detected_categories"] = list(dict.fromkeys(
        "money" if c == "investment_decision" else "career" if c == "business" else c for c in categories))
    # Real facts still needed for _context_lead_in's acknowledge/reframe step
    # (Phase 9/10) — kept under a separate key so the OLD generic
    # _life_context_hint mechanism below still sees an empty life_context and
    # doesn't repeat personal_context's blurb a second time in the same reply.
    render_context["_life_context_for_lead_in"] = context.get("life_context", {})
    render_context["life_context"] = {}  # personalized once below, not a repeated generic hint
    parts = []
    if context.get("resolved_prediction_feedback"):
        verdict = context["resolved_prediction_feedback"]["verdict"]
        parts.append(choose(language,
            "Thank you for correcting that. I have recorded your feedback without changing your chart calculations." if verdict == "incorrect" else "Thank you. I have recorded your feedback as your report, without changing the chart calculations.",
            "धन्यवाद। आपकी प्रतिक्रिया दर्ज कर ली है; कुंडली की गणना नहीं बदली है।"))
    personal = personal_context(context, language)
    if personal:
        parts.append(personal)
    if categories and categories != ["memory_recall"]:
        framing = practical_framing(context, language)
        if framing:
            parts.append(framing)
        parts.append(await TemplateInterpreter().chat_reply(history, render_context, language))
    elif not parts:
        parts.append(choose(language, "I have noted what you shared. What would you like to explore next?", "आपकी बात दर्ज कर ली है। आगे आप क्या समझना चाहेंगे?", "Aapki baat note kar li hai. Aage kya samajhna chahenge?"))
    events = context.get("validated_events", [])
    if events:
        event = events[0]
        parts.append(choose(language,
            f"You reported {event['description']} ({event['year']}). I am using that as your lived context, not as proof that a prediction was correct.",
            f"आपने बताया था: {event['description']} ({event['year']})। यह आपका अनुभव है, भविष्यवाणी की पुष्टि का प्रमाण नहीं।"))
    feedback = context.get("prediction_feedback", [])
    if feedback and feedback[0].get("verdict") == "incorrect":
        parts.append(choose(language, "You previously marked a related prediction as incorrect; I will not treat it as a validated event.", "आपने पिछली संबंधित भविष्यवाणी गलत बताई थी; उसे पुष्ट घटना नहीं माना गया है।"))
    previous = context.get("retrieved_history", [])
    # Caught live: suppressing personal_context's redundant "relationship
    # status: married" line (see _has_marital_reframe above) made `personal`
    # empty more often for exactly these categories — which made the "not
    # personal" gate below let the quote-callback through MORE, not less,
    # the opposite of the intent. A category whose OWN lead-in already
    # personalizes the reply (_context_lead_in, templates.py) counts as
    # personalized here too, even though it renders after this point.
    if previous and not personal and not _has_marital_reframe(context):
        # A historical quote is explicitly historical, never promoted to a
        # current fact (the user may have corrected or deleted that memory).
        quote = previous[0]
        if quote.get("source") == "user_quote":
            parts.append(choose(language,
                f"In an earlier related conversation you said: “{quote['text']}”. If that situation has changed, tell me so I can use your current circumstances.",
                f"पिछली संबंधित बातचीत में आपने कहा था: “{quote['text']}”। यदि स्थिति बदल गई है तो बताएं।"))
    if context.get("follow_up_questions"):
        parts.append(context["follow_up_questions"])
    # context["decision_missing"] used to append a fixed caveat here
    # ("...treat this as conditional guidance rather than a recommendation
    # to act") on every incomplete decision, regardless of the person or
    # question — internal reasoning about the engine's own confidence,
    # not something a human astrologer would say out loud by default. Per
    # direct, explicit feedback: keep this internal. The still-missing
    # slots are already visible as the numbered follow-up question above
    # when there is one; that already does the real work of asking for
    # what's needed, without a separate disclaimer sentence.
    return "\n\n".join(parts)


# problem_next_steps and decision_next_steps used to live here — a fixed,
# generic checklist ("Compare three options: ... Next steps: speak with
# potential customers and suppliers...") appended to EVERY problem/decision
# reply regardless of the specific person, verbatim identical for anyone
# with the same category. Removed per direct, explicit feedback: this is
# exactly the "extra text which should not be there" complaint, and the
# same "would this apply to a million people?" test this session has
# already used to justify removing other generic filler. The real,
# person-specific guidance (DECISION_SLOTS' own questions, the computed
# timing window, prediction_service's own reasoning text) already carries
# the actual content; this block added length and templated-sounding
# checklist prose without adding anything specific to the person asking.
