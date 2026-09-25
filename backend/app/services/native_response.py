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


_CATEGORIES_WITH_BUSINESS_REFRAME = frozenset(("career", "workplace_problem", "career_confusion"))


def _has_business_reframe(context) -> bool:
    """Same idea as _has_marital_reframe, for _context_lead_in's OTHER
    reframe (templates.py's career/business branch: "Since you're focused
    on X, here's how that reads rather than a generic career answer...").
    Caught live, reproduced: a "career" turn with a known business fact got
    BOTH that reframe AND the quote-callback below verbatim-quoting the
    SAME old business message right after it ("Pichli baat-cheet mein
    aapne kaha tha: '1 clothings and yes i have costumenrs...'") — visibly
    duplicated personalization, the exact "repeating stored context"
    complaint. Mirrors _context_lead_in's own condition exactly so the two
    never drift apart."""
    business = (context.get("life_context") or {}).get("business", {})
    life_state = context.get("life_state") or {}
    return bool(
        _CATEGORIES_WITH_BUSINESS_REFRAME.intersection(context.get("detected_categories") or ())
        and (business.get("business_type") or life_state.get("business_state") in ("running", "considering"))
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


# "change_reason"/"alternative_opportunity" (both written exclusively by
# job_change_decision's own DECISION_SLOTS questions — see
# conversation_engine.QUESTIONS) are deliberately absent from
# _CLAUSE_TEMPLATES below, not just scoped to their one category the way
# an earlier version of this fix did: _named_facts_sentence already
# synthesizes them into a real, forward-moving sentence for
# job_change_decision ("Stress is what's driving this, and you already
# have another offer...") — showing them again here as a second, flatter
# clause right next to that synthesis was redundant, the same "restating
# what was just said" complaint this whole function exists to avoid.


# Caught live, direct product feedback: "From what you've shared, your
# work: Job in IT sector; your financial buffer: some." reads as a
# database dump, not something a person would say — even shown only
# ONCE (shown_facts, above, already stops it repeating every turn; this
# is a separate problem: the FORMAT itself). Each key here is now a
# CLAUSE template (a full "you ___" fragment, not a noun-phrase label),
# joined into one flowing sentence by _join_clauses instead of "; ".
# change_reason/alternative_opportunity were removed entirely rather than
# converted — _named_facts_sentence (below) already synthesizes them into
# a real sentence for job_change_decision; showing them again here was a
# second, redundant "label: value" line right next to that synthesis.
_CLAUSE_TEMPLATES = {
    "occupation": ("you work as {v}", "आप {v} के रूप में काम करते हैं", "aap {v} ke roop mein kaam karte hain"),
    "industry": ("you're in the {v} field", "आप {v} क्षेत्र में हैं", "aap {v} field mein hain"),
    "transition_intent": ("you're considering {v}", "आप {v} पर विचार कर रहे हैं", "aap {v} par vichar kar rahe hain"),
    "business_type": ("you're exploring {v}", "आप {v} की संभावना देख रहे हैं", "aap {v} explore kar rahe hain"),
    "savings": ("you have {v} set aside", "आपके पास {v} बचत है", "aapke paas {v} savings hai"),
    "financial_responsibilities": ("you have {v} to manage", "आपकी {v} जिम्मेदारियां हैं", "aapki {v} zimmedariyan hain"),
    "relationship_status": ("you are {v}", "आप {v} हैं", "aap {v} hain"),
    "children_count": ("you have {v} children", "आपके {v} बच्चे हैं", "aapke {v} bachche hain"),
    "planning_intent": ("you're {v}", "आप {v} कर रहे हैं", "aap {v} kar rahe hain"),
    "spouse_name": ("your spouse is {v}", "आपके जीवनसाथी {v} हैं", "aapke jeevansaathi {v} hain"),
}
# "stage" is an internal enum (has_customers/early_revenue — see
# native_understanding.extract_knowledge), not free text, so it needs its
# own natural phrasing per value rather than a generic {v} slot.
_BUSINESS_STAGE_CLAUSES = {
    "has_customers": ("your business already has customers", "आपके व्यवसाय के पास पहले से ग्राहक हैं", "aapke business ke paas pehle se customers hain"),
    "early_revenue": ("your business is already generating some revenue", "आपका व्यवसाय पहले से ही कुछ आय कमा रहा है", "aapka business pehle se kuch revenue generate kar raha hai"),
}


def _join_clauses(clauses, language):
    if len(clauses) == 1:
        return clauses[0]
    connector = choose(language, "and", "और", "aur")
    if len(clauses) == 2:
        return f"{clauses[0]} {connector} {clauses[1]}"
    return f"{', '.join(clauses[:-1])}, {connector} {clauses[-1]}"


def personal_context(context, language):
    facts = context.get("life_context", {})
    skip_relationship_status = _has_marital_reframe(context)
    # Caught live: "your financial buffer: four months of savings" (this
    # function) right next to "...With four months of savings to fall back
    # on, there's real room to plan this properly..." (_named_facts_sentence,
    # which reads the SAME money.savings fact as job_change_decision's
    # "runway" slot) — the identical fact stated twice, once flat and once
    # synthesized, in the same reply. Only job_change_decision's own
    # DECISION_SLOTS flow reads savings this way; a plain money/savings
    # question elsewhere still shows it normally.
    skip_savings = "job_change_decision" in (context.get("detected_categories") or ())
    # Caught live: "I want to switch to business" writes the SAME concept
    # under two domains with two DIFFERENT literal values — career.
    # transition_intent="business" (career_direction's own DECISION_SLOTS
    # fact key) and business.transition_intent="start a business" (see
    # native_understanding.extract_knowledge) — rendering "you're
    # considering business and you're considering start a business" back to
    # back, an awkward near-duplicate the value/clause-level dedupe below
    # can't catch since the two VALUES genuinely differ. business's own
    # value is the more specific/informative of the two.
    skip_career_transition_intent = bool(
        (facts.get("business") or {}).get("transition_intent", {}).get("value")
    )
    # Caught live, direct product feedback: "your work: Job in IT sector"
    # (and similarly for other stable facts) got restated on EVERY career-
    # related turn for an entire conversation, not just the turn it was
    # first established — a real person doesn't re-confirm something you
    # already told them every time you speak. `shown_facts`, when the
    # caller provides it (chat.py persists it turn to turn via
    # ConversationState — see that call site), is a set of "domain:key:
    # value" identities already surfaced at least once THIS conversation;
    # a fact already shown is skipped, and any fact newly shown here gets
    # added to the set (mutated in place) so the caller can persist it.
    # None (the default for any caller/test that doesn't pass it, e.g. a
    # single one-shot call with no conversation state) disables this
    # entirely — every eligible fact always shows, the original behavior.
    shown_facts = context.get("shown_facts")
    clauses = []
    seen = set()
    seen_clauses = set()
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
            if key == "savings" and domain == "money" and skip_savings:
                continue
            if key == "transition_intent" and domain == "career" and skip_career_transition_intent:
                continue
            value = str(fact["value"])
            if fact.get("source") not in ("user_stated", "user_confirmed") or fact.get("confidence") == "low" or value in seen:
                continue
            # Caught live, reproducing the exact leak this function exists to
            # prevent: DECISION_SLOTS writes free-text answers under internal
            # slot keys ("goal", "funding", "customer_supplier_contacts"...)
            # that were never given a clause template below. Those keys
            # already get real natural-language synthesis
            # (_named_facts_sentence) — an untemplated key is skipped here
            # rather than raw-dumped.
            if key == "stage":
                clause_template = _BUSINESS_STAGE_CLAUSES.get(value)
                if clause_template is None:
                    continue
                clause = choose(language, *clause_template)
            elif key in _CLAUSE_TEMPLATES:
                # Captured lowercase like every other free-text extraction
                # (see native_understanding.py's extract_knowledge) — a
                # proper noun reads as personal, not a data-entry glitch.
                display_value = value.title() if key == "spouse_name" else _humanize_raw_token(value)
                clause = choose(language, *_CLAUSE_TEMPLATES[key]).format(v=display_value)
            else:
                continue
            # A single statement ("I want to switch to business") can write
            # the SAME key under two different domains with two slightly
            # different literal values (career.transition_intent="business",
            # business.transition_intent="start a business" — see
            # native_understanding.extract_knowledge) — caught live: this
            # rendered the identical clause twice back to back. The
            # value-only `seen` check above doesn't catch it since the
            # values differ; dedupe by the rendered clause too.
            if clause in seen_clauses:
                continue
            if shown_facts is not None:
                fact_identity = f"{domain}:{key}:{value}"
                if fact_identity in shown_facts:
                    continue
                shown_facts.add(fact_identity)
            seen.add(value)
            seen_clauses.add(clause)
            clauses.append(clause)
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
        clauses.append(choose(language,
            f"your goal is {recent_goals[0]}" if len(recent_goals) == 1 else f"your goals have included {_join_clauses(recent_goals, language)}",
            f"आपका लक्ष्य {recent_goals[0]} है" if len(recent_goals) == 1 else f"आपके लक्ष्यों में {_join_clauses(recent_goals, language)} शामिल रहे हैं",
            f"aapka goal {recent_goals[0]} hai" if len(recent_goals) == 1 else f"aapke goals mein {_join_clauses(recent_goals, language)} shaamil rahe hain"))
    if not clauses:
        return ""
    lead = choose(language, "You've mentioned that ", "आपने बताया कि ", "Aapne bataya ki ")
    stop = "।" if language == "hi" else "."
    return lead + _join_clauses(clauses[:5], language) + stop


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


# Classical Vedic significations (planet -> the kind of work/trade it
# governs) — direct product ask: once business_start_decision's own
# questions are answered, name a SPECIFIC suited industry from the chart
# instead of only restating what the person already said back to them
# ("it's up to you which business you continue, but astrologically you
# have a good hand for X — worth giving that a try too"). Deliberately
# framed as one option worth considering, never as a verdict overriding
# their own stated choice — the chart adds a data point, it doesn't
# replace the decision.
_INDUSTRY_SUGGESTIONS_EN: dict[str, str] = {
    "Su": "leadership-facing work — government liaison, administration, or anything where you're the visible face of the operation",
    "Mo": "food, beverages, or hospitality — anything public-facing and people-oriented",
    "Ma": "engineering, electricals, machinery, or metalwork — hands-on, technical trades",
    "Me": "trade, media, writing, or consulting — anything built on communication",
    "Ju": "education, finance, or advisory work — teaching or guiding others",
    "Ve": "fashion, beauty, design, or the arts — anything aesthetic or experience-driven",
    "Sa": "real estate, manufacturing, or steady, labor-intensive trades built for the long haul",
    "Ra": "technology, import-export, or unconventional, fast-moving fields",
    "Ke": "research, healing, or specialized, behind-the-scenes work",
}
_INDUSTRY_SUGGESTIONS_HI: dict[str, str] = {
    "Su": "नेतृत्व से जुड़ा काम — प्रशासन, सरकारी संपर्क, या जहां आप सबसे आगे नज़र आएं",
    "Mo": "खाना, पेय पदार्थ, या हॉस्पिटैलिटी — कुछ भी जो लोगों से सीधा जुड़ा हो",
    "Ma": "इंजीनियरिंग, बिजली का काम, मशीनरी, या धातु से जुड़ा काम — हाथों से किया जाने वाला तकनीकी काम",
    "Me": "व्यापार, मीडिया, लेखन, या कंसल्टिंग — संवाद पर आधारित कोई भी काम",
    "Ju": "शिक्षा, वित्त, या सलाहकार का काम — पढ़ाना या दूसरों को मार्गदर्शन देना",
    "Ve": "फैशन, ब्यूटी, डिज़ाइन, या कला — कुछ भी सौंदर्य या अनुभव पर केंद्रित",
    "Sa": "रियल एस्टेट, मैन्युफैक्चरिंग, या मेहनत वाला स्थिर, लंबी अवधि का काम",
    "Ra": "टेक्नोलॉजी, आयात-निर्यात, या नए, तेज़ी से बदलते क्षेत्र",
    "Ke": "शोध, उपचार, या विशेष, पर्दे के पीछे का काम",
}


def _business_industry_suggestion(strongest_planet_code, language):
    suggestion = (_INDUSTRY_SUGGESTIONS_HI if language == "hi" else _INDUSTRY_SUGGESTIONS_EN).get(strongest_planet_code)
    if not suggestion:
        return None
    return choose(language,
        f"It's genuinely up to you which business you continue with — but astrologically, you have a good hand for "
        f"{suggestion}, so that's worth considering too.",
        f"आगे कौन सा व्यवसाय जारी रखना है, यह पूरी तरह आपकी पसंद है — लेकिन ज्योतिष के अनुसार, आपका हाथ {suggestion} में "
        f"अच्छा बैठता है, तो इसे भी एक विकल्प के तौर पर देखा जा सकता है।")


def _named_facts_sentence(category, facts, language, strongest_planet_code=None, shown_facts=None):
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
        # Caught live (Scenario E, personal-astrologer chat upgrade plan): a
        # business type stated as a plain first-person assertion ("I want to
        # start a clothing business") is extracted straight to
        # business.business_type, a DIFFERENT key from business.goal (which
        # only ever gets written by actually ANSWERING the business_goal
        # QUESTION). conversation_engine.known_slot already aliases the two
        # for gating purposes (so the question is correctly never re-asked),
        # but this rendering read "goal" only — silently never naming the
        # business type back to the user even though it was genuinely known.
        goal, funding = val(business, "goal") or val(business, "business_type"), val(business, "funding")
        if not any((goal, funding)):
            return None
        funding_clause = _as_clause(funding) if funding else funding
        if goal and funding:
            sentence = choose(language,
                f"You're thinking {goal}, funded by {funding_clause} — that's the actual combination worth "
                f"weighing against the timing below, not a generic business question.",
                f"आप {goal} सोच रहे हैं, {funding_clause} के सहारे — नीचे के समय को इसी संयोजन के आधार पर देखना चाहिए, किसी "
                f"सामान्य व्यवसाय सवाल के आधार पर नहीं।")
            # Direct product ask: once the decision-critical questions are
            # actually answered (both goal and funding known — the "final
            # question" moment), name a specific suited industry from the
            # chart instead of stopping at just restating what they said.
            # Caught live, direct follow-up feedback: without its own
            # shown_facts gate, this re-stated on EVERY later business turn
            # once goal+funding were known — "add it for the situation, not
            # every chat." A synthetic identity (not a real domain/key/value
            # triple, but the same set) marks it said once per conversation.
            industry = _business_industry_suggestion(strongest_planet_code, language)
            if industry and shown_facts is not None:
                industry_identity = f"industry_suggestion:{category}:{strongest_planet_code}"
                if industry_identity in shown_facts:
                    industry = None
                else:
                    shown_facts.add(industry_identity)
            return f"{sentence} {industry}" if industry else sentence
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
    strongest_planet_code = context.get("strongest_planet_code")
    shown_facts = context.get("shown_facts")
    return "\n\n".join(
        s for c in categories
        if (s := _named_facts_sentence(c, facts, language, strongest_planet_code, shown_facts))
    )


async def compose(history, context, language):
    categories = context.get("detected_categories", [])
    render_context = dict(context)
    # Keep the existing specialized calculation-to-text paths. These aliases
    # reuse only computed house facts; they do not create new predictions.
    # Caught live: bare "business" remapping to "career" here reintroduced
    # the generic house-10 career reading (and its "since you're focused on
    # X, here's how that reads rather than a generic career answer" reframe)
    # right back into chat_reply's answer list even after chat.py had
    # deliberately excluded "career" once business_category_suitability was
    # the active, more specific ask — section 12 (personal-astrologer chat
    # upgrade correction): suitability and generic career timing must stay
    # distinct, never silently reblended just because this alias exists.
    _has_specific_outlook = any(c in ("business_category_suitability", "financial_stability") for c in categories)
    render_context["detected_categories"] = list(dict.fromkeys(
        "money" if c == "investment_decision"
        else "career" if c == "business" and not _has_specific_outlook
        else c
        for c in categories
    ))
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
    # Caught live: chat.py calls personal_context() a SECOND time after
    # compose() returns, to check whether THIS reply was already
    # personalized (gating the "in an earlier conversation you said..."
    # quote-callback). With shown_facts' dedup now mutating state on every
    # call, that second call would see everything as "already shown" (this
    # call just marked it) and always report empty, even though this reply
    # genuinely was personalized — wrongly gating the quote-callback open
    # every single time instead of only when nothing else personalized the
    # reply. Cached here so chat.py can reuse the real result instead of
    # calling personal_context() again.
    context["_personal_context_result"] = personal
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
    if previous and not personal and not _has_marital_reframe(context) and not _has_business_reframe(context):
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
