"""Conservative, provider-free conversation understanding.

Only explicit first-person assertions become facts. Unsupported language remains
unknown and is clarified, never inferred by a remote model. This vocabulary is
deliberately extensible without changing astronomical calculations.
"""
import re
from datetime import date

from rapidfuzz.distance import DamerauLevenshtein

from app.services.chat_understanding import (
    ChatUnderstanding, ContextUpdate, DecisionUpdate, EventUpdate,
    ImportantDateUpdate, LifeStateUpdate, PredictionFeedbackReport,
)
from app.services.interpretation.templates import (
    _detect_categories, _fuzzy_word_matches_keyword, _SUB_INTENT_HOUSE_ALIAS, message_is_affirmative_reply,
    message_is_negative_reply, message_is_greeting,
)


def choose(language, en, hi, hinglish=None):
    return hi if language == "hi" else hinglish if language == "hinglish" and hinglish else en


# A message that's itself a question isn't a "situation" to reference back
# later (see chat_memory_service.retrieve_native_turns and native_response
# .compose's "if that situation has changed" callback) — this is the exact
# check conversation_engine.resume() already used inline for its own,
# different purpose (deciding whether a reply switches topic); exposed here
# as the one shared home both modules import from, rather than duplicated.
def is_question(text: str) -> bool:
    """A request for information, not a stated fact — never a "situation" to
    quote back with "if that has changed." Caught live: "Tell me about my
    marriage prospects" has no "?" and doesn't start with an interrogative,
    but is exactly as nonsensical to quote back as a real question is. Same
    for "I want to ask about my relationship" — caught live, the exact
    message got quoted back to the SAME user as "an earlier related
    conversation" they supposedly need to update, which is nonsensical for
    a request that was never a stated fact in the first place.

    Deliberately does NOT also cover bare navigational words ("relationship",
    "career") — see is_navigational_reply below for that, kept separate
    because conversation_engine.resume()'s pending_domain_clarification gate
    needs is_question to stay False for exactly those words to resolve them
    via _resolve_domain_word."""
    text_lower = text.lower()
    return bool(
        "?" in text
        or re.search(r"^(?:when|why|how|should|what|kab|kya|कब|क्या)\b", text_lower)
        or re.search(r"^(?:tell\s+(?:me|us)|explain|describe|show\s+(?:me|us))\b", text_lower)
        or re.search(r"^(?:बताओ|बताइए|बताएं|बताइये)\b", text.strip())
        or re.search(r"\bi want to (?:ask|know)\b|\bmujhe (?:janna|jaanna|puchna|poochna)\b|\bjaanna chahta\b|\bjaanna chahti\b", text_lower)
    )


# Bare, one-or-two-word domain/menu replies — "relationship", "career", a
# numbered menu pick — are navigation, not autobiographical statements about
# the user's life. Caught live: "relationship" (a one-word reply picking a
# topic, nothing more) got quoted back later as "an earlier related
# conversation you said" — nonsensical for a word that was never a stated
# fact to begin with. Kept separate from is_question (see its own docstring
# for why) — used only by chat_memory_service's "is this quotable as a
# situation" filter, not by conversation_engine's topic-switch detection.
_NAVIGATIONAL_WORDS = {
    "relationship", "relationships", "marriage", "career", "job", "work", "money", "business",
    "family", "health", "education", "today", "week", "dasha",
    "rishta", "shaadi", "kaam", "naukri", "paisa", "vyapar", "parivar",
    "रिश्ता", "शादी", "काम", "नौकरी", "पैसा", "व्यापार", "परिवार",
}


def is_navigational_reply(text: str) -> bool:
    words = text.lower().strip(" ?.!").split()
    return bool(1 <= len(words) <= 2 and all(w in _NAVIGATIONAL_WORDS or w.isdigit() for w in words))


# The literal tokens extract_knowledge's own patterns below depend on as
# EXACT words — caught live: "i am alrady married" (typo for "already")
# silently failed to extract anything at all, because the marital-status
# regex has zero tolerance for an unrecognized filler word between "am" and
# "married". A message word within fuzzy distance of one of these gets
# corrected to the canonical spelling before any pattern runs — reusing the
# EXACT SAME edit-distance/first-letter-guard tolerance already proven in
# templates.py's topic detection, not a new fuzzy implementation. Curated
# on purpose (not a full spell-checker): only the words these patterns
# actually anchor on, grown over time as real typos surface — the same
# scoped-exception philosophy as templates.py's own _NO_FUZZY_KEYWORDS.
_FACT_ANCHOR_WORDS = [
    "already", "currently", "married", "single", "unmarried", "divorced", "engaged", "widowed",
    "unemployed", "employed", "developer", "engineer", "teacher", "doctor", "designer", "manager",
    "accountant", "student", "nurse", "consultant", "software", "technology", "finance", "healthcare",
    "education", "retail", "business", "company", "customers", "paying", "ecommerce", "planning",
    "pregnant", "expecting", "children", "savings", "salary", "offer", "leaving", "leave",
    "quitting", "quit", "because", "renting", "parents", "mortgage", "experience", "family",
    "about", "goal", "prefer", "trying", "baby", "thinking", "considering",
    # Hinglish distress words — caught live: "shhadi" (typo for "shaadi")
    # went uncorrected, so a real distress message ("main shhadi se dukhi
    # hoon") matched only the generic "marriage" topic, missing the
    # relationship_conflict distress signal entirely.
    "shaadi", "dukhi", "pareshan",
    # "marrige" (a real, common typo for "marriage" — missing the second
    # "a") went uncorrected for the same reason: only "married" (the
    # adjective) was an anchor word, not "marriage" (the noun) — so "there
    # is a problem in my marrige" matched only the generic "marriage" topic
    # instead of relationship_conflict's "problem in my marriage" pattern.
    "marriage",
]


def _fuzzy_normalize(text: str) -> str:
    corrected_words = []
    for word in text.split(" "):
        core = re.sub(r"[^a-z]", "", word)
        if not core or core in _FACT_ANCHOR_WORDS:
            corrected_words.append(word)
            continue
        # Closest match by actual edit distance, not the first anchor word
        # in list order that happens to satisfy the threshold — caught
        # live: "marrige" (typo for "marriage") got corrected to "married"
        # instead, purely because "married" sits earlier in the anchor list
        # and was ALSO within tolerance, even though "marriage" is the
        # objectively closer match (distance 1 vs 2). List order should
        # never silently decide which of two real, similar words wins.
        candidates = [a for a in _FACT_ANCHOR_WORDS if _fuzzy_word_matches_keyword(core, a)]
        match = min(candidates, key=lambda a: DamerauLevenshtein.distance(core, a)) if candidates else None
        corrected_words.append(word.replace(core, match, 1) if match else word)
    return " ".join(corrected_words)


def onboarding_slot(topic, question):
    """Map recognized question meanings, not arbitrary prompts, to memory keys."""
    text = question.lower()
    domain = {"marriage": "relationships", "personal_direction": "goals"}.get(topic, topic)
    if domain not in {"career", "business", "relationships", "money", "family", "goals"}:
        return None
    patterns = (
        (r"what do you (?:currently )?do|अभी.*काम|abhi.*(?:kaam|karte)", "occupation"),
        (r"how long|कितने समय|kitne (?:time|samay)", "experience"),
        (r"what's your business|व्यवसाय क्या|business kya", "business_type"),
        (r"currently in a relationship|are you married|क्या आप.*(?:शादी|रिश्ते)|kya aap.*(?:shaadi|relationship)", "relationship_status"),
        (r"goal|लक्ष्य|lakshya", "top_goal"),
        (r"on your mind|making you think|clarity|going on with|चिंता|सोच|mann|soch", "main_concern"),
    )
    return next(((domain, key) for pattern, key in patterns if re.search(pattern, text)), None)


# The generic "marriage" bucket (house 7) collapses every relationship
# question into one answer regardless of what's actually being asked —
# caught live: "I want to ask about relationship" got the exact same
# reply a "when will I get married" question would, for a user who is
# already married. These sub-intents are checked BEFORE the bare
# "marriage" catch-all below so a more specific ask is never also tagged
# generic — rendered via templates.py's alias to the same house-7 data
# (no new astrology), just a different, honest opening framing per intent.
_RELATIONSHIP_CATEGORIES = frozenset((
    "marriage_timing", "marriage_decision", "spouse_relationship", "relationship_conflict", "family_planning",
))
_SUB_INTENT_PATTERNS = (
    (r"\b(?:fight|fighting|conflict|argument|arguments|problem|problems|issues?) (?:with|in) (?:\w+ )?"
     r"(?:marriage|relationship|spouse|wife|husband|partner)\b|rishte mein.*(?:jhagda|problem)|रिश्ते में.*झगड़ा"
     # Distress/unhappiness about the marriage itself — caught live: "main
     # shaadi se dukhi hoon" (I am unhappy because of my marriage) has no
     # "fight"/"conflict"/"problem" word at all, so it fell through to the
     # exact same neutral "married life" answer a plain status check would
     # get, completely ignoring that this is a distress signal, not a
     # request for a generic reading.
     r"|\b(?:dukhi|pareshan|udaas|naraz)\b.*\b(?:shaadi|rishte|partner|pati|patni)\b"
     r"|\b(?:shaadi|rishte)\b.*\b(?:dukhi|pareshan|udaas)\b"
     r"|\b(?:unhappy|upset|sad|struggling|miserable) (?:in|with|about) (?:my )?(?:marriage|relationship)\b"
     # "We both don't get along" — caught live: no "fight"/"conflict"/
     # "unhappy" word at all, so this fell through to zero categories
     # entirely (not even the generic "marriage" catch-all), landing on the
     # fully generic "what do you want to talk about" clarifying question
     # even immediately after a relationship topic was already the subject.
     r"|\b(?:we|i) (?:both )?(?:do not|don't|dont|doesn't|doesnt|does not) get along\b"
     r"|\bnot getting along\b|nahi bante\b|nahi bantee\b|nahi patt rahi\b|नहीं बनती\b|नहीं बनते\b"
     r"|दुखी.*शादी|शादी.*दुखी|परेशान.*शादी|शादी.*परेशान",
     "relationship_conflict"),
    (r"\b(?:bonding|connection|compatibility|understanding) with (?:my )?(?:spouse|wife|husband|partner)\b"
     r"|\bmy (?:spouse|wife|husband|partner)(?:'s)? relationship\b|\bmarried life\b|shaadi.*zindagi|वैवाहिक जीवन",
     "spouse_relationship"),
    (r"\bfamily planning\b|\bplanning (?:a |for a )?family\b|\btrying for a baby\b"
     r"|parivar niyojan|पारिवारिक नियोजन",
     "family_planning"),
    (r"\b(?:problem|issue|conflict|fight) (?:at|with) (?:work|office|my boss|my colleague|my manager)"
     r"|workplace.*(?:problem|issue|conflict)|office mein.*problem|ऑफिस में.*समस्या",
     "workplace_problem"),
    (r"\b(?:confused|unsure|not sure|lost|don't know what to do) about (?:my )?career"
     r"|career (?:confusion|direction)\b|career.*samajh nahi|करियर.*समझ नहीं",
     "career_confusion"),
    (r"\b(?:my )?(?:loan|debt|karza|कर्ज़|कर्ज)\b.*\b(?:pay|repay|clear|chukana)\b|\bhow (?:do i|to) (?:pay off|clear) (?:my )?(?:loan|debt)\b",
     "debt"),
    (r"\bfinancial stability\b|\bfinancially stable\b|आर्थिक स्थिरता",
     "financial_stability"),
)

# Extra topic categories a sub-intent is a genuine superset of, BEYOND its
# own _SUB_INTENT_HOUSE_ALIAS parent — caught live: "family planning" (the
# sub-intent) and "family" (the bare topic) aren't alias parent/child, but
# the word "family" is literally both the sub-intent's own trigger phrase
# AND a _TOPIC_KEYWORDS["family"] keyword, so both matched the same message
# and got answered as two separate, concatenated templates.
_SUB_INTENT_ALSO_SUPPRESSES: dict[str, tuple[str, ...]] = {
    "family_planning": ("family",),
    # "get along" (the relationship_conflict trigger above) is ALSO a
    # _TOPIC_KEYWORDS["friends"] phrase — caught live: "we don't get along"
    # matched both, same double-template-concatenation risk as
    # family_planning/family above.
    "relationship_conflict": ("friends",),
}


def detect_intents(message, birth_year=None):
    text = message.lower()
    # Typo-corrected copy, used for every plain-regex check below (decision
    # patterns, sub-intent patterns, the business/marriage catch-alls) —
    # caught live: "shhadi" (typo for "shaadi") went uncorrected and a real
    # distress message matched only the generic "marriage" topic, missing
    # the relationship_conflict signal entirely. Also caught live: "I want
    # to switch to buisness" (a common transposition typo) matched NONE of
    # these plain regexes (only literal "business"), even though
    # extract_knowledge's fact extraction already correctly recognized it
    # via this same normalization — so the message got tagged bare
    # "career" only and answered with stale job-change timing instead of
    # ever being recognized as a business-transition message. Deliberately
    # NOT applied to `_detect_categories(text, ...)` below — that function
    # already does its own, separately-tuned per-keyword fuzzy matching
    # across a much larger keyword surface, and layering this correction on
    # top of it is unverified/out of scope here.
    normalized_text = _fuzzy_normalize(text)
    categories = _detect_categories(text, birth_year)
    if re.search(r"what (?:do you know|do you remember|have i told you) about me|मेरे बारे में.*याद|mere baare.*yaad", text):
        return ["memory_recall"]
    additions = []
    for pattern, category in (
        (r"(?:should|shall|can) i (?:leave|quit|change|switch).*?(?:job|work)|naukri.*(?:chhod|badal)|नौकरी.*(?:छोड़|बदल)", "job_change_decision"),
        (r"(?:should|shall|can) i (?:start|launch).*?(?:business|company)|business shuru|व्यवसाय शुरू", "business_start_decision"),
        (r"(?:should|shall|can) i (?:invest|buy stocks)|invest kar|निवेश कर", "investment_decision"),
        (r"(?:should|shall|can) i (?:move|relocate).*?(?:abroad|country)|videsh.*(?:ja|shift)|विदेश.*जा", "relocation_decision"),
    ):
        if re.search(pattern, normalized_text):
            additions.append(category)
    for pattern, category in _SUB_INTENT_PATTERNS:
        if category in additions or not re.search(pattern, normalized_text):
            continue
        # Relationship sub-intents are mutually exclusive with each other and
        # with marriage_timing/marriage_decision — a message shouldn't get
        # tagged both "family_planning" and the generic "marriage" catch-all
        # below. Career/finance sub-intents (workplace_problem etc.) have no
        # such sibling group, so only self-dedupe.
        if category in _RELATIONSHIP_CATEGORIES and any(c in _RELATIONSHIP_CATEGORIES for c in categories + additions):
            continue
        additions.append(category)
    if re.search(r"\b(?:business|company|customers|ecommerce|entrepreneur)\b|व्यवसाय|व्यापार", normalized_text) and not any("business" in c for c in categories + additions):
        additions.append("business")
    if (
        re.search(r"\b(?:relationship|spouse|wife|husband|partner)\b", normalized_text)
        and not any(c in _RELATIONSHIP_CATEGORIES or "marriage" in c for c in categories + additions)
    ):
        additions.append("marriage")
    # A sub-intent already names the specific angle a plain "marriage"/
    # "career"/"money" match from _detect_categories above would otherwise
    # ALSO add (e.g. "wife" is itself a _TOPIC_KEYWORDS["marriage"] keyword,
    # so "married life with my wife" matches both) — drop the redundant
    # generic parent rather than answering the same house twice in one reply.
    for sub_intent, parent in _SUB_INTENT_HOUSE_ALIAS.items():
        if sub_intent not in additions:
            continue
        # Caught live: "yes, Family planning" matched BOTH the
        # family_planning sub-intent AND the generic bare "family" topic
        # (the word "family" is literally one of _TOPIC_KEYWORDS["family"]),
        # and since neither is the OTHER'S _SUB_INTENT_HOUSE_ALIAS parent
        # (family_planning aliases to "marriage", not "family"), the earlier
        # version of this loop only ever dropped "marriage" — leaving both
        # "family_planning" and "family" in the final list, so chat_reply
        # answered BOTH and concatenated a relationship template with a
        # family template into one reply. Suppress any OTHER topic a
        # sub-intent is a known superset of, not just its own alias parent.
        suppress = {parent} | set(_SUB_INTENT_ALSO_SUPPRESSES.get(sub_intent, ()))
        categories = [c for c in categories if c not in suppress]
    return list(dict.fromkeys(additions + categories))[:3]


def extract_knowledge(message):
    """Return explicit facts, current state, dated events, and concrete deadlines."""
    # Quoted examples/instructions are not autobiographical assertions.
    text = re.sub(r'"[^"\n]*"|“[^”\n]*”', '', message).lower().replace("’", "'")
    text = _fuzzy_normalize(text)
    # "im" (no apostrophe) is an extremely common way "I'm" actually gets
    # typed — caught live: "im married" extracted nothing at all, because
    # every "i am|i'm X" pattern below (occupation, unemployed, pregnant,
    # marital status, etc.) requires the apostrophe or the space-separated
    # "am". Normalized once here rather than patched into all 9 patterns
    # individually.
    text = re.sub(r"\bim\b", "i am", text)
    facts = {}
    state = {}
    retractions: list[tuple[str, str]] = []

    def put(domain, key, value):
        value = str(value).strip(" .,;:")[:240]
        if value:
            facts[domain, key] = ContextUpdate(domain, key, value, "high", "user_stated")

    # Clause boundaries keep a negation/hypothetical from leaking into a fact.
    clauses = re.split(r"[.!?;\n]|\bbut\b|\blekin\b|लेकिन", text)
    for clause in clauses:
        clause = clause.strip()
        if re.search(r"^(?:what if|if |suppose|imagine|my friend|he |she |they |do you think|am i |should i )|\b(?:used to|previously|formerly)\b", clause):
            continue
        role = re.search(r"\bi (?:work as|am working as|am|'m) (?:a |an )?(?P<role>software engineer|software developer|developer|engineer|teacher|doctor|designer|manager|accountant|student|nurse|consultant|business owner)\b", clause)
        if not role:
            role = re.search(r"(?:main|मैं) (?P<role>developer|engineer|teacher|डॉक्टर|इंजीनियर|शिक्षक)(?: hoon| हूं| हूँ)", clause)
        if role:
            put("career", "occupation", role["role"])
            state["career_state"] = "student" if role["role"] == "student" else "employed"
        if re.search(r"\bmy software job\b", clause):
            put("career", "industry", "software")
            state["career_state"] = "employed"
        industry = re.search(r"\bi work in (software|technology|finance|healthcare|education|retail)\b", clause)
        if industry:
            put("career", "industry", industry[1])
            state["career_state"] = "employed"
        if re.search(r"\bi (?:am|'m) (?:currently )?(?:unemployed|not employed|out of work)|meri naukri nahi|मैं बेरोजगार", clause):
            state["career_state"] = "unemployed"
        for pattern, status in (
            (
                r"\bi (?:am|'m) (?:already |currently )?(?:a )?married\b"
                # "I got married" states a completed event that IS a current
                # status, not just a timeline entry (see the events loop
                # below, which records the dated event separately) — caught
                # live: stating this never updated marital_status at all.
                r"|\bi (?:got|have got) married\b"
                # Hinglish idioms — "shaadi shuda" (married, lit. "marriage-
                # having") and "married hu/hoon" (English word + Hindi verb)
                # were entirely unrecognized; only pure-Hindi "shaadi ho
                # chuki" existed before.
                r"|\bshaadi\s*shuda\b|\bmarried\s*(?:hu|hoon)\b"
                r"|meri shaadi ho chuki|मेरी शादी हो चुकी|शादीशुदा",
                "married",
            ),
            (r"\bi (?:am|'m) (?:currently )?(?:single|not married|unmarried)\b|meri shaadi nahi|मेरी शादी नहीं", "single"),
            (r"\bi (?:am|'m) divorced\b", "divorced"),
            (r"\bi (?:am|'m) engaged\b", "engaged"),
            (r"\bi (?:am|'m) widowed\b", "widowed"),
        ):
            if re.search(pattern, clause):
                state["marital_status"] = status
                put("relationships", "relationship_status", status)
        # Spouse's name — genuinely absent before this (Phase 1 gap): every
        # personalized "you and X" callback needs it, but nothing extracted
        # it at all. Values are captured lowercase, same convention as every
        # other free-text extraction here (see occupation/change_reason
        # above) — native_response.py title-cases it for display.
        spouse_name = re.search(r"\bmy (?:wife|husband|spouse)(?:'s name)? (?:is|named|called) ([a-z]+)\b", clause)
        if spouse_name:
            put("relationships", "spouse_name", spouse_name[1])
        children = re.search(r"\bi have (\d+|one|two|three|no) (?:children|kids|child)\b", clause)
        if children:
            count = {"one": 1, "two": 2, "three": 3, "no": 0}.get(children[1], children[1])
            state["children_count"] = int(count)
            put("family", "children_count", count)
        if re.search(r"\bi (?:am|'m) (?:pregnant|expecting a baby)\b", clause):
            state["pregnancy_status"] = "expecting"
        if re.search(r"\bi (?:am not|am no longer|'m not) pregnant\b", clause):
            state["pregnancy_status"] = "none"
        # Considering a child, not currently pregnant — a real, distinct
        # intent from pregnancy_status above (caught live: "we are thinking
        # about family planning" was extracting nothing at all, unlike the
        # analogous business.transition_intent pattern below).
        if re.search(
            r"\b(?:we|i) (?:are |am )?(?:thinking about|planning|considering|discussing) family planning\b"
            r"|\bplanning (?:a |for a )?family\b|\bwant(?:ing)? (?:to have )?(?:a )?(?:baby|child)\b"
            r"|\btrying for a baby\b|parivar niyojan|पारिवारिक नियोजन",
            clause,
        ):
            put("family", "planning_intent", "considering family planning")
        if re.search(r"\bi (?:want|plan|hope|am planning|am thinking) (?:to |about )?(?:start|starting|build|building|launch|launching|switch|switching|shift|shifting) (?:to |into )?.*?(?:business|company)|\bi am thinking about leaving.*and starting.*(?:business|company)|business shuru karna|व्यवसाय शुरू करना", clause):
            put("business", "transition_intent", "start a business")
            put("career", "transition_intent", "business")
            state["business_state"] = "considering"
        if re.search(r"\b(?:i|my business) (?:already )?have (?:paying )?customers\b", clause):
            put("business", "stage", "early_revenue" if "paying" in clause else "has_customers")
            state["business_state"] = "running"
        if re.search(r"\bi (?:run|own) (?:a |an |my )?.*?(?:business|company|shop)\b", clause):
            state["business_state"] = "running"
        # Caught live: "i dont have business it was just an idea" — a direct
        # retraction of an already-stored business.stage="has_customers"
        # fact from an earlier turn — extracted nothing at all, so the stale
        # fact kept being echoed back turn after turn even after the user
        # said otherwise. Checked AFTER the "has customers"/"run business"
        # patterns above so an explicit negation always wins if a single
        # message somehow matches both. Same "no longer current" signal as
        # the pregnancy_status negation above, plus the 3 business facts
        # that only ever mean something if a business is actually real.
        if re.search(
            r"\bi (?:don't|do not|dont)(?: actually)? (?:have|run|own) (?:a |my |any )?(?:business|company)\b"
            r"|\b(?:business|company)\b.{0,25}\b(?:was|is) (?:just|only) an idea\b",
            clause,
        ):
            state["business_state"] = "none"
            retractions.extend((
                ("business", "stage"), ("business", "transition_intent"), ("business", "business_type"),
            ))
        if "ecommerce" in clause or "e-commerce" in clause:
            if re.search(r"\bi\b|\bmy\b", clause) and not re.search(r"\b(?:not|don't|never)\b", clause):
                put("business", "business_type", "ecommerce")
        product = re.search(r"\bi (?:want|plan|am planning|am thinking).*?(?:business (?:selling|in|of)|sell(?:ing) )\s*(.+?)(?=\band i\b|$)", clause)
        if product and not re.search(r"\b(?:don't|do not|no longer)\b", clause):
            put("business", "business_type", product[1])
        if re.search(r"\bmy job has no growth|\bi (?:am|'m) (?:stuck|stressed) (?:at|with|in) (?:my )?(?:job|work)\b|job mein growth nahi|नौकरी में.*विकास नहीं", clause):
            put("career", "main_concern", "lack of job growth" if "growth" in clause or "विकास" in clause else "work stress")
        if re.search(r"\b(?:my partner and i|we) (?:fight|are fighting)\b", clause):
            put("relationships", "main_concern", "relationship conflict")
        if re.search(r"\bi (?:am struggling|have trouble) (?:with|paying|repaying).*?loan", clause):
            put("money", "main_concern", "loan repayment pressure")
        for pattern, domain, key in (
            (r"\bi work (?:at|for) ([\w &-]+?)(?=,|\band\b|$)", "career", "employer"),
            (r"\bi have (\d+ years?)(?: of)? experience", "career", "experience"),
            (r"\b(?:my salary is|i earn) ([\w ₹$€,.]+?)(?=\band\b|$)", "money", "salary_range"),
            # Caught live: "...yes i have customers, 2 i have some savings and
            # i'll do this business parttime" (a numbered reply typed without
            # periods) had the lazy capture group span straight through the
            # SECOND "i have", since digits/commas/spaces are all valid class
            # members — capturing "customers, 2 i have some" as the "savings"
            # value. The negative lookahead stops the capture the instant it
            # would swallow another "i have", without narrowing what a
            # genuine single savings answer ("six months", "50000 rupees") can
            # contain.
            (r"\bi have ((?:(?!\bi have\b)[\w ₹$€,-])+?) (?:in savings|of savings|savings)", "money", "savings"),
            (r"\bi (?:support|am responsible for) (my [\w ]+?)(?=,|\band\b|$)", "family", "financial_responsibilities"),
            (r"\bmy (?:career )?goal is (.+)", "goals", "top_goal"),
            (r"\bi prefer (.+)", "preferences", "communication_preference"),
        ):
            match = re.search(pattern, clause)
            if match:
                put(domain, key, match[1])
        if re.search(r"\bi (?:have|already have|received) (?:a |an |another )?(?:job )?offer\b", clause):
            put("career", "alternative_opportunity", "job offer available")
        if re.search(r"\bi (?:don't|do not) have (?:another |a |any )?(?:job )?offer|\bno (?:job )?offer\b", clause):
            put("career", "alternative_opportunity", "no job offer")
        if re.search(r"\bi (?:am |am thinking about |want to |plan to )?(?:leaving|leave|quitting|quit).*?job", clause):
            put("career", "considering_job_change", "true")
        reason = re.search(r"\bi (?:want to|am planning to|am thinking about).*?(?:leave|leaving|change|quit).*?(?:because of|because|for) (.+)", clause)
        if reason:
            put("career", "change_reason", reason[1])
        if re.search(r"\bi (?:own|already own) (?:a |my )?(?:house|home|property)\b", clause):
            state["housing_status"] = "owns_property"
        if re.search(r"\bi (?:am renting|rent a|live with my parents)\b", clause):
            state["housing_status"] = "living_with_parents" if "parents" in clause else "renting"
        if re.search(r"\bi have (?:a |an )?(?:home loan|mortgage)\b", clause):
            state["has_home_loan"] = True
        if re.search(r"\bi (?:have no|don't have a|do not have a) (?:home loan|mortgage)\b", clause):
            state["has_home_loan"] = False

    events = []
    for pattern, kind in (
        (r"\bi (?:changed jobs|switched jobs|started a new job|joined)", "new_job"),
        (r"\bi (?:got married|married)", "marriage"),
        (r"\bi (?:was promoted|got promoted)", "promotion"),
        (r"\bi (?:started|launched) (?:a |my )?(?:business|company)", "started_business"),
        (r"\bi moved (?:to|abroad)", "moved_city"),
        (r"\bi (?:had a baby|became a parent)", "became_parent"),
    ):
        for clause in clauses:
            if not re.search(pattern, clause) or re.search(r"\b(?:if|would|might|not|never)\b", clause):
                continue
            year_match = re.search(r"\b(19\d{2}|20\d{2})\b", clause)
            ago = re.search(r"\b(\d+) years? ago\b", clause)
            year = int(year_match[1]) if year_match else date.today().year - int(ago[1]) if ago else date.today().year - 1 if "last year" in clause else None
            if year and 1900 <= year <= date.today().year:
                events.append(EventUpdate(kind, clause.strip(), year))
    deadline = None
    match = re.search(r"\b(?:my .+? is on|my goal is .+? by|i .+? by) (\d{4}-\d{2}-\d{2})\b", text)
    if match:
        try:
            target = date.fromisoformat(match[1])
            if target > date.today():
                deadline = ImportantDateUpdate("goals", message[:240], target.isoformat())
        except ValueError:
            pass
    return list(facts.values()), LifeStateUpdate(**state) if state else None, events, deadline, retractions


# Phase 8 — Answer Capability Resolver, deliberately minimal: a general,
# reusable REFUSE mechanism (not a one-off if-statement buried in understand)
# so more genuinely unanswerable questions can be added here later without
# new plumbing. Starts with the concrete case from the spec — child gender —
# which the engine would otherwise silently fall through to the generic
# Lagna-intro fallback on, never actually declining. An honest "I can't
# answer that, here's what I can help with instead" beats both a guess and
# silence.
_CAPABILITY_REFUSALS = (
    (
        r"\b(?:boy or girl|baby'?s? gender|child'?s? gender|will (?:it|the baby|my baby) be a (?:boy|girl))\b"
        r"|ladka hoga ya ladki|बेटा होगा या बेटी",
        (
            "I can't predict a child's gender — that isn't something astrology determines, so I won't guess. "
            "I can help with family planning timing, the pregnancy phase itself, or parenting themes instead. "
            "Which of those would help?",
            "मैं बच्चे का लिंग नहीं बता सकता — यह ज्योतिष तय नहीं करता, इसलिए मैं अंदाज़ा नहीं लगाऊंगा। मैं परिवार नियोजन का समय, "
            "गर्भावस्था के चरण, या पेरेंटिंग से जुड़े विषयों में मदद कर सकता हूं। इनमें से क्या मददगार होगा?",
        ),
    ),
)


def _capability_refusal(message: str, language: str) -> str | None:
    text = message.lower()
    for pattern, (en, hi) in _CAPABILITY_REFUSALS:
        if re.search(pattern, text):
            return choose(language, en, hi)
    return None


def understand(history, birth_year, language, open_decisions=None,
               pending_outcome_checkins=None, pending_reconfirmation=None,
               current_life_state=None, pending_prediction_feedback=None,
               pending_important_date=None):
    message = history[-1]["content"] if history else ""
    refusal = _capability_refusal(message, language)
    if refusal:
        result = ChatUnderstanding(categories=[])
        result.needs_clarification = True
        result.clarifying_question = refusal
        return result
    categories = detect_intents(message, birth_year)
    result = ChatUnderstanding(categories=categories)
    (
        result.context_updates, result.life_state_update, result.events,
        result.important_date_update, result.retracted_facts,
    ) = extract_knowledge(message)
    previous = history[-2]["content"] if len(history) > 1 and history[-2]["role"] == "assistant" else ""
    yes = message_is_affirmative_reply(message) or message.strip().startswith(("हाँ", "हां"))
    no = message_is_negative_reply(message) or message.strip().startswith("नहीं")
    text = message.lower()
    # Follow-up resolution requires the actual immediately preceding prompt.
    if pending_prediction_feedback and previous.startswith(pending_prediction_feedback["question_asked"]) and not "?" in message:
        verdict = "partial" if re.search(r"\b(?:partly|partially|somewhat)\b", text) else "not_sure" if re.search(r"\b(?:not sure|don't remember)\b", text) else "correct" if yes or result.events else "incorrect" if no else None
        if verdict:
            result.prediction_feedback = PredictionFeedbackReport(verdict, message if verdict in ("correct", "partial") else None)
    if pending_reconfirmation and pending_reconfirmation["value"] in previous and (yes or "still the same" in text):
        result.reconfirmed = True
    if pending_outcome_checkins and re.search(r"how did that go|how has it|how has that|how did it|कैसा रहा", previous.lower()) and not "?" in message:
        result.outcome_report = message[:500]
    if pending_important_date and pending_important_date["description"] in previous and not "?" in message:
        result.important_date_outcome = message[:500]
    for decision in open_decisions or []:
        if re.search(r"\bi (?:have )?decided (?:to|against)|\bi (?:abandoned|cancelled) (?:the |my )?plan", text):
            # Only resolve the decision explicitly named in this assertion.
            if decision.get("category") in categories:
                result.decision_update = DecisionUpdate(decision["category"], "abandoned" if re.search(r"against|abandoned|cancelled", text) else "decided", message[:240])
        explicit_choices = {
            "job_change_decision": r"\bi (?:accepted (?:the |a |another )?(?:job|offer)|decided to (?:stay|leave|quit)|changed jobs)\b",
            "business_start_decision": r"\bi (?:started|launched|decided to start) (?:a |my )?(?:business|company)\b",
            "relocation_decision": r"\bi (?:moved|decided to move) (?:to|abroad)\b",
            "house_purchase_decision": r"\bi (?:bought|decided to buy) (?:a |the )?(?:house|home|property)\b",
            "marriage_decision": r"\bi (?:got married|decided to marry)\b",
            "investment_decision": r"\bi (?:invested|decided (?:not )?to invest)\b",
        }
        if re.search(explicit_choices.get(decision.get("category"), r"(?!)"), text):
            result.decision_update = DecisionUpdate(decision["category"], "decided", message[:240])
    if not categories and message and not message_is_greeting(message) and not any((result.context_updates, result.events, result.prediction_feedback, result.reconfirmed, result.outcome_report, result.important_date_outcome)):
        result.needs_clarification = True
        result.clarifying_question = choose(language,
            "What situation would you like to understand—work, relationships, money, business, or family? Tell me what has changed or what you are deciding.",
            "आप काम, रिश्ते, पैसा, व्यवसाय या परिवार में किस स्थिति को समझना चाहते हैं? क्या बदला है या आप किस निर्णय पर विचार कर रहे हैं?",
            "Aap kaam, relationships, paisa, business ya family mein kya samajhna chahte hain? Kya badla hai, ya kaunsa decision lena hai?")
    return result
