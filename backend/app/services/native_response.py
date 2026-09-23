"""Personalized interpretation of computed facts, before optional styling."""
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


def personal_context(context, language):
    facts = context.get("life_context", {})
    skip_relationship_status = _has_marital_reframe(context)
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
            value = str(fact["value"])
            # Captured lowercase like every other free-text extraction (see
            # native_understanding.py's extract_knowledge) — a proper noun
            # reads as personal, not as a data-entry glitch, when displayed.
            display_value = value.title() if key == "spouse_name" else value
            if fact.get("source") not in ("user_stated", "user_confirmed") or fact.get("confidence") == "low" or value in seen:
                continue
            seen.add(value)
            label = choose(language, *labels[key]) if key in labels else key.replace("_", " ")
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


def _named_facts_sentence(category, facts, language):
    """Phase 14 — the interpretation should reference the SPECIFIC facts
    conversation_engine's DECISION_SLOTS already collected for this category,
    not only a generic caveat that never repeats back what the user actually
    said. No astrology calculation changes: prediction_service's verdict is
    untouched, this only enriches the interpretation text around it with
    values already sitting in context["life_context"]."""
    career, money, business, relationships = (
        facts.get(d, {}) for d in ("career", "money", "business", "relationships")
    )

    def val(bucket, key):
        return bucket.get(key, {}).get("value")

    if category == "job_change_decision":
        reason, offer, runway = val(career, "change_reason"), val(career, "alternative_opportunity"), val(money, "savings")
        known = [v for v in (reason, offer, runway) if v]
        if not known:
            return None
        pieces_en = [p for p in (
            f"your stated reason is {reason}" if reason else None,
            f"your situation is: {offer}" if offer else None,
            f"your savings runway is {runway}" if runway else None,
        ) if p]
        pieces_hi = [p for p in (
            f"आपकी बताई वजह है: {reason}" if reason else None,
            f"आपकी स्थिति है: {offer}" if offer else None,
            f"आपकी बचत रनवे है: {runway}" if runway else None,
        ) if p]
        return choose(language,
            f"Specifically, {'; '.join(pieces_en)} — weigh the timing below against that, not a generic scenario.",
            f"विशेष रूप से, {'; '.join(pieces_hi)} — नीचे के समय को इसी के आधार पर तौलें, किसी सामान्य स्थिति के आधार पर नहीं।")
    if category == "business_start_decision":
        goal, funding = val(business, "goal"), val(business, "funding")
        known = [v for v in (goal, funding) if v]
        if not known:
            return None
        pieces_en = [p for p in (f"your plan is: {goal}" if goal else None, f"your funding is: {funding}" if funding else None) if p]
        pieces_hi = [p for p in (f"आपकी योजना है: {goal}" if goal else None, f"आपका धन स्रोत है: {funding}" if funding else None) if p]
        return choose(language,
            f"Specifically, {'; '.join(pieces_en)} — weigh the timing below against that.",
            f"विशेष रूप से, {'; '.join(pieces_hi)} — नीचे के समय को इसी के आधार पर तौलें।")
    if category == "marriage_decision":
        constraints = val(relationships, "marriage_constraints")
        if not constraints:
            return None
        return choose(language,
            f"Specifically, you mentioned: {constraints} — that concern doesn't disappear just because the timing looks supportive.",
            f"विशेष रूप से, आपने बताया: {constraints} — समय अनुकूल दिखने से यह चिंता खत्म नहीं हो जाती।")
    return None


def practical_framing(context, language):
    categories = context.get("detected_categories", [])
    facts = context.get("life_context", {})
    career, business = facts.get("career", {}), facts.get("business", {})
    alternative = career.get("alternative_opportunity", {}).get("value", "").lower()
    if "job_change_decision" in categories and any(term in alternative for term in ("no offer", "no job offer", "none", "नहीं")):
        return choose(language,
            "You have said there is no offer yet. Compare staying while applying or testing the business with a planned career break funded by your savings. The chart window cannot supply the missing income plan.",
            "आपने बताया कि अभी प्रस्ताव नहीं है। नौकरी करते हुए आवेदन या व्यवसाय का परीक्षण करने और बचत से नियोजित विराम लेने की तुलना करें। कुंडली आय की योजना का विकल्प नहीं है।")
    if any(c in categories for c in ("career", "job_change_decision", "business_start_decision", "business")) and ("transition_intent" in career or "business_type" in business):
        return choose(language,
            "This is a job-versus-business transition, so compare keeping your income while testing customer demand with leaving for the venture. The timing below is relevant to that transition; it does not establish whether the business can cover your commitments.",
            "यह नौकरी और व्यवसाय के बीच बदलाव का प्रश्न है। आय जारी रखते हुए ग्राहकों की मांग परखने और नौकरी छोड़कर व्यवसाय करने की तुलना करें। नीचे का समय इस बदलाव से संबंधित है; इससे व्यवसाय की आय की गारंटी नहीं मिलती।",
            "Yeh job-versus-business transition hai. Current income rakhkar customer demand test karne aur job chhodne ko compare karein. Neeche ki timing transition se judi hai; business income ki guarantee nahi hai.")
    rules = {
        "job_change_decision": (
            "Compare staying, accepting a concrete offer, and resigning without one against the goal and savings you described. A supportive chart window is not a job offer or a replacement for income.",
            "अपने लक्ष्य और बचत के अनुसार रुकने, ठोस प्रस्ताव स्वीकारने और बिना प्रस्ताव नौकरी छोड़ने की तुलना करें। अनुकूल समय नौकरी या आय का विकल्प नहीं है।"),
        "business_start_decision": (
            "Use your customer evidence, funding and ongoing commitments to decide the size of a trial before committing fully. The chart timing supports planning; it cannot establish demand or profit.",
            "पूरी प्रतिबद्धता से पहले ग्राहकों की मांग, धन और जिम्मेदारियों के आधार पर छोटा परीक्षण तय करें। कुंडली का समय मांग या मुनाफा सिद्ध नहीं करता।"),
        "relocation_decision": (
            "Separate the travel window from the practical choice: compare work or visa eligibility, housing costs and the reason for moving before choosing a date.",
            "यात्रा के समय से व्यावहारिक निर्णय अलग रखें: तारीख चुनने से पहले काम, वीज़ा, घर का खर्च और स्थान बदलने की वजह की तुलना करें।"),
        "house_purchase_decision": (
            "Match the property timing to your stated purpose, down payment and affordable repayments. Ownership indicators cannot establish affordability or legal suitability.",
            "संपत्ति के समय को अपने उद्देश्य, डाउन पेमेंट और वहनीय किस्त से जोड़ें। कुंडली वहनीयता या कानूनी उपयुक्तता तय नहीं करती।"),
        "marriage_decision": (
            "Use the timing alongside your relationship readiness, shared expectations and responsibilities. Your chart alone cannot establish compatibility with a particular partner.",
            "समय के साथ रिश्ते की तैयारी, साझा अपेक्षाएं और जिम्मेदारियां देखें। केवल आपकी कुंडली किसी खास साथी से अनुकूलता तय नहीं कर सकती।"),
        "investment_decision": (
            "Your financial goal, time horizon, emergency savings and ability to absorb loss determine which options are realistic. Astrology cannot estimate investment returns or recommend a security; the wealth indicators below are only a timing reflection.",
            "वित्तीय लक्ष्य, समय सीमा, आपात बचत और नुकसान सहने की क्षमता से विकल्प तय होंगे। ज्योतिष निवेश का रिटर्न या प्रतिभूति नहीं चुन सकता; नीचे के धन संकेत केवल समय पर विचार हैं।"),
    }
    base = "\n\n".join(choose(language, *rules[c]) for c in categories if c in rules)
    named = "\n\n".join(s for c in categories if (s := _named_facts_sentence(c, facts, language)))
    return "\n\n".join(p for p in (base, named) if p)


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
    if context.get("decision_missing"):
        parts.append(choose(language, "The practical details are still incomplete, so treat this as conditional guidance rather than a recommendation to act.", "व्यावहारिक जानकारी अभी अधूरी है; इसे सशर्त मार्गदर्शन मानें, कदम उठाने की सलाह नहीं।"))
    return "\n\n".join(parts)
