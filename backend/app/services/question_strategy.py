"""Question intent and memory relevance are separate from astrology categories."""
import re
from datetime import datetime, timedelta, timezone

from app.services.chat_understanding import ContextUpdate
from app.services.native_understanding import choose

FOCUS_OPTIONS = {
    "career": (
        ("career", "Current job growth", "वर्तमान नौकरी में विकास", "Current job growth"),
        ("job_change_decision", "Job change", "नौकरी बदलना", "Job change"),
        ("business_start_decision", "Business transition", "व्यवसाय की ओर बदलाव", "Business transition"),
        ("career", "General career direction", "करियर की सामान्य दिशा", "General career direction"),
    ),
    "marriage": (
        ("marriage", "Current relationship", "वर्तमान रिश्ता", "Current relationship"),
        ("marriage", "Relationship growth", "रिश्ते में सुधार", "Relationship growth"),
        ("marriage_timing", "Marriage timing", "विवाह का समय", "Shaadi ki timing"),
    ),
    "money": (
        ("money", "Loan or financial pressure", "ऋण या आर्थिक दबाव", "Loan ya financial pressure"),
        ("wealth_timing", "Income and wealth growth", "आय और धन में वृद्धि", "Income aur wealth growth"),
        ("investment_decision", "An investment decision", "निवेश का निर्णय", "Investment decision"),
    ),
    "family": (
        ("family", "A current family concern", "परिवार की वर्तमान चिंता", "Current family concern"),
        ("children", "Children or family planning", "बच्चे या परिवार की योजना", "Children ya family planning"),
        ("family", "Family relationships generally", "सामान्य पारिवारिक रिश्ते", "General family relationships"),
    ),
    "business": (
        ("business", "Existing business growth", "मौजूदा व्यवसाय में वृद्धि", "Existing business growth"),
        ("business_start_decision", "Starting a business", "व्यवसाय शुरू करना", "Business shuru karna"),
        ("business_partnership_timing", "Business partnership", "व्यावसायिक साझेदारी", "Business partnership"),
    ),
}


def question_type(message, categories):
    text = message.lower().strip(" .?!")
    if any(c.endswith("_decision") for c in categories) or re.search(r"\b(?:should|shall) i\b", text):
        return "decision"
    if re.search(r"\b(?:still good|still relevant|still suitable|is this right)\b|abhi bhi.*(?:sahi|achha)|अभी भी.*(?:ठीक|अच्छा)", text):
        return "confirmation"
    if any(c in ("relationship_conflict", "career_confusion", "workplace_problem") for c in categories) or re.search(r"\b(?:no growth|stuck|stress|struggling|fights|fighting|problem|worried|debt|pressure)\b|तनाव|परेशान|झगड़|growth nahi|pareshan", text):
        return "problem"
    if any(c.endswith("_timing") for c in categories) or re.search(r"\bwhen\b|\bkab\b|कब", text):
        return "prediction"
    if text in {"career", "job", "business", "money", "finance", "relationship", "relationships", "family", "marriage", "करियर", "नौकरी", "व्यवसाय", "पैसा", "रिश्ता", "परिवार", "शादी"}:
        return "clarification"
    if re.fullmatch(r"(?:tell me about|how is|how's|what about|explain|discuss) (?:my |our )?(?:career|job|business|money|finances|relationship|relationships|family|marriage)(?: generally| in general| looking)?", text):
        return "clarification"
    return "information"


def focus_domain(categories):
    for category in categories:
        if category in FOCUS_OPTIONS:
            return category
        if "business" in category:
            return "business"
        if "career" in category or "job" in category:
            return "career"
        if "marriage" in category or "relationship" in category or "spouse" in category:
            return "marriage"
        if "wealth" in category or "investment" in category:
            return "money"
        if "children" in category:
            return "family"
    return None


def resolve_focus(understanding, message, state, language):
    confirmed_at = state.get("focus_confirmed_at")
    if confirmed_at:
        try:
            expired = datetime.now(timezone.utc) - datetime.fromisoformat(confirmed_at) > timedelta(hours=24)
        except (ValueError, TypeError):
            expired = True
        if expired:
            for key in ("focus_confirmed", "confirmed_fact_ids", "excluded_fact_ids", "focus_confirmed_at"):
                state.pop(key, None)
    pending = state.get("focus_pending")
    if not pending:
        return [], []
    text = message.lower().strip(" .")
    options = FOCUS_OPTIONS[pending["domain"]]
    selected = None
    if re.fullmatch(r"[1-4]", text):
        index = int(text) - 1
        selected = options[index] if index < len(options) else None
    for option in options:
        if any(label.lower() in text for label in option[1:]):
            selected = option
    confirm = bool(re.match(r"^(?:yes|haan|हाँ|हां)\b", text)) or text in {"same plan", "still relevant", "same concern"}
    refs = pending.get("facts", [])
    # "but its not about fights" — caught live: the fixed reject phrase list
    # above (no longer/not anymore/abandoned/...) never matches a plain,
    # very common denial that instead directly names and negates the
    # remembered thing itself ("it's not about X", "not X", "wasn't about
    # X"). Left unrecognized, neither confirm nor reject fired, so
    # focus_pending was never cleared and the SAME remembered fact ("you
    # mentioned you're worried about fights") kept resurfacing turn after
    # turn even after the user explicitly said it was wrong. A general
    # negation word ("not"/"nahi") co-occurring with a real content word
    # from the remembered fact's own text is treated as rejecting it — the
    # user naming the thing they're denying is itself the strongest signal
    # available, stronger than requiring one of a fixed phrase list.
    _NEGATION_RE = re.compile(r"\b(?:not|nahi|nahin|नहीं)\b")
    reject = (
        bool(re.search(r"\b(?:no longer|not anymore|not now|abandoned|dropped|cancelled)\b|अब नहीं|ab nahi", text))
        or text in {"no", "nahi", "नहीं"}
        or bool(_NEGATION_RE.search(text) and any(
            any(word in text for word in re.findall(r"\w{4,}", f["value"].lower())) for f in refs
        ))
    )
    confirmed, inactive = [], []
    if confirm and selected is None:
        confirmed = refs
        selected = options[pending.get("remembered_option", 0)]
    elif reject:
        inactive = refs
        state["dismissed_memory_values"] = list(dict.fromkeys(
            state.get("dismissed_memory_values", []) + [f["value"] for f in refs]))
    if selected:
        understanding.categories = [selected[0]]
        understanding.needs_clarification = False
        understanding.clarifying_question = None
        state["focus_confirmed"] = selected[0]
        state["focus_confirmed_at"] = datetime.now(timezone.utc).isoformat()
        # Choosing general/job growth must not silently confirm a business plan.
        if selected == options[pending.get("remembered_option", 0)] and not reject:
            confirmed = refs
        state["confirmed_fact_ids"] = [f["id"] for f in confirmed]
        state["excluded_fact_ids"] = [f["id"] for f in refs if f not in confirmed]
        state["pending"] = []
        state["asked"] = []
        state["categories"] = understanding.categories
        # Every bare-category gate conversation_engine.questions_for() owns
        # (career/marriage/money/family) must be suppressed once a focus
        # here is confirmed — caught live: picking "A current family
        # concern" (-> bare category "family") immediately hit
        # questions_for()'s OWN family menu right after, showing two
        # clarifying menus back to back for one simple mention. Setting all
        # four sticky flags (not just the two this function originally
        # knew about) keeps this correct regardless of which domain the
        # picked option happens to resolve to.
        state["career_clarified"] = True
        state["marriage_clarified"] = True
        state["money_clarified"] = True
        state["family_clarified"] = True
        state.pop("focus_pending", None)
    elif reject:
        state.pop("focus_pending", None)
        state["confirmed_fact_ids"] = []
        understanding.categories = [pending["domain"]]
        understanding.needs_clarification = True
        understanding.clarifying_question = choose(language,
            "Understood—I will treat that earlier concern as inactive. What would you like to focus on now?",
            "समझ गया। उस पुरानी चिंता को अब निष्क्रिय मानूंगा। अभी किस बात पर ध्यान देना चाहते हैं?",
            "Samajh gaya. Purani concern ko inactive maanunga. Ab kis baat par focus karna hai?")
    elif understanding.categories:
        state.pop("focus_pending", None)  # explicit new question supersedes the menu
    for fact in confirmed:
        understanding.context_updates.append(ContextUpdate(fact["domain"], fact["key"], fact["value"], "high", "user_confirmed"))
        state["dismissed_memory_values"] = [v for v in state.get("dismissed_memory_values", []) if v != fact["value"]]
    return confirmed, inactive


def relevance_question(message, categories, context, state, language, updates):
    kind = question_type(message, categories)
    domain = focus_domain(categories)
    current = {(u.domain, u.key) for u in updates}
    confirmed_ids = set(state.get("confirmed_fact_ids", []))
    excluded_ids = set(state.get("excluded_fact_ids", []))
    memories = []
    for group, facts in context.get("life_context", {}).items():
        for key, fact in facts.items():
            if kind != "clarification" and fact.get("id") in excluded_ids:
                continue
            if kind != "clarification" and state.get("focus_confirmed") in ("career", "job_change_decision") and (group == "business" or "transition" in key):
                continue
            if (group, key) in current or (kind != "clarification" and fact.get("id") in confirmed_ids):
                continue
            # "relationship" as a bare substring only ever matches
            # "relationship_status" in this app's key vocabulary — caught
            # live: a plain marital-status fact ("married") got treated as
            # recall-worthy content and surfaced as "you previously
            # mentioned: married, is that still relevant?", crowding out
            # the actual concern (concern_type: "frequent fights...") that
            # should have been the one recalled. A status fact isn't a
            # stated plan/concern the way every other term here is —
            # excluded explicitly rather than dropping "relationship"
            # wholesale, in case a future key legitimately needs it.
            if key == "relationship_status":
                continue
            if any(term in key for term in ("goal", "concern", "plan", "interest", "business_type", "transition", "loan", "relationship", "problem")):
                memories.append({"domain": group, "key": key, **fact})
    needs_focus = kind == "clarification" and bool(memories)
    stale = [f for f in memories if f.get("relevance") in ("RECENT", "HISTORICAL")]
    needs_confirmation = kind == "confirmation" or bool(stale)
    if not domain or not (needs_focus or needs_confirmation):
        return None
    # Any broad topic clears the earlier conversational focus, even if it is
    # asked minutes later. Remembering a plan is not choosing today's goal.
    state["confirmed_fact_ids"] = []
    state["excluded_fact_ids"] = []
    chosen = memories if needs_focus else stale or memories
    if domain == "career":
        chosen.sort(key=lambda f: f["key"] != "business_type")
    chosen = chosen[:2]
    recalled = "; ".join(f["value"] for f in chosen)
    opening = choose(language,
        f"You previously mentioned: {recalled}. Is that still relevant, or are you asking about something else now?" if recalled else "Which aspect would you like to focus on now?",
        f"आपने पहले बताया था: {recalled}। क्या यह अभी भी प्रासंगिक है, या अब किसी और पहलू के बारे में पूछ रहे हैं?" if recalled else "अभी किस पहलू पर ध्यान देना चाहते हैं?",
        f"Aapne pehle bataya tha: {recalled}. Kya abhi bhi wahi concern hai, ya ab kisi aur aspect par focus karna hai?" if recalled else "Ab kis aspect par focus karna chahte hain?")
    remembered = 2 if domain == "career" and any(f["domain"] == "business" or "business" in f["value"].lower() for f in chosen) else 0
    state["focus_pending"] = {"domain": domain, "facts": chosen, "remembered_option": remembered}
    state.pop("focus_confirmed", None)
    for key in ("pending_intent_menu", "pending_concern_menu", "pending_situation_check", "pending_domain_clarification"):
        state.pop(key, None)
    state["pending"] = []
    options = FOCUS_OPTIONS[domain]
    return opening + "\n\n" + "\n".join(f"{i}. {choose(language, *o[1:])}" for i, o in enumerate(options, 1))


def usable_facts(context, state, updates):
    current = {(u.domain, u.key) for u in updates}
    confirmed = set(state.get("confirmed_fact_ids", []))
    out = {}
    for domain, facts in context.get("life_context", {}).items():
        selected = {key: value for key, value in facts.items()
                    if (domain, key) in current or (
                        value.get("id") not in state.get("excluded_fact_ids", [])
                        and (value.get("id") in confirmed or value.get("relevance", "ACTIVE") == "ACTIVE"))}
        # A selected job/general-career focus is not permission to use an old
        # business idea, even if that idea is very recent.
        if state.get("focus_confirmed") in ("career", "job_change_decision"):
            selected = {k: v for k, v in selected.items() if domain != "business" and "transition" not in k}
        if selected:
            out[domain] = selected
    return out
