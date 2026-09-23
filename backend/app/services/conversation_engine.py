"""Persistent intent resolution and decision-critical questions. No provider calls."""
import re

from sqlalchemy import select

from app.db.models.conversation_state import ConversationState
from app.services.chat_understanding import ContextUpdate
from app.services.native_understanding import choose, detect_intents, is_question
from app.services.interpretation.templates import message_is_affirmative_reply, message_is_negative_reply

# A one-word reply to native_understanding.understand()'s own generic
# "work/relationships/money/business/family?" clarifying question has no
# `pending` slot to bind to — DECISION_SLOTS' mechanism below only covers
# the 6 decision types. Resolved via this small, explicit map instead of
# re-running the bare word through full intent detection, which is what
# silently dropped "kaam" (Hindi for "work") in the first place — it isn't
# a career keyword anywhere, so re-detecting it would fail exactly the same
# way twice. Deliberately narrow: this only ever fires when the state below
# confirms the generic question was just asked, never for an ordinary message.
_DOMAIN_WORDS = {
    "career": ("kaam", "job", "naukri", "career", "काम", "नौकरी", "करियर"),
    "money": ("paisa", "money", "पैसा", "पैसे"),
    # "relationships" (plural) — caught live: a real reply of exactly
    # "relationships" (not "relationship") matched neither the exact-equals
    # nor the startswith-plus-space check below, so this whole gate silently
    # did nothing and the message fell through to full category detection
    # with marital status not yet known, giving a full generic timing answer
    # instead of resolving the pending domain question.
    "marriage": ("rishta", "relationship", "relationships", "shaadi", "रिश्ता", "शादी"),
    "business": ("business", "vyapar", "व्यापार", "व्यवसाय"),
    "family": ("family", "parivar", "परिवार"),
}


def _resolve_domain_word(message: str) -> str | None:
    text = message.strip().lower()
    for category, words in _DOMAIN_WORDS.items():
        if any(text == w or text.startswith(w + " ") for w in words):
            return category
    return None

# Stable slot IDs decouple answer storage from translated question wording.
# A slot is asked only for decisions where its answer changes practical framing.
QUESTIONS = {
    "reason": ("career", "change_reason", "What is driving the change: growth, money, stress, or something else?", "बदलाव की वजह क्या है: विकास, पैसा, तनाव या कुछ और?", "Badlav ki wajah growth, paisa, stress ya kuch aur hai?"),
    "offer": ("career", "alternative_opportunity", "Do you have another offer, or are you choosing between a job and a business?", "क्या आपके पास दूसरा प्रस्ताव है, या आप नौकरी और व्यवसाय में चुनाव कर रहे हैं?", "Kya doosra offer hai, ya job aur business mein chunna hai?"),
    "runway": ("money", "savings", "What savings or dependable income would cover your commitments during the transition?", "बदलाव के दौरान खर्च और जिम्मेदारियां किस बचत या स्थिर आय से पूरी होंगी?", "Transition mein kharche kis savings ya regular income se chalenge?"),
    "business_goal": ("business", "goal", "What would you sell, and have you tested demand with customers?", "आप क्या बेचेंगे, और क्या ग्राहकों के साथ मांग परखी है?", "Kya bechenge, aur customers ke saath demand test ki hai?"),
    "funding": ("business", "funding", "How would you fund the business, and would you keep your current income while testing it?", "व्यवसाय के लिए धन कहां से आएगा, और क्या परीक्षण के दौरान वर्तमान आय जारी रहेगी?", "Business ka funding kaise hoga, aur testing ke dauran current income rahegi?"),
    "move_goal": ("preferences", "relocation_goal", "Is the move for work, family, or lifestyle, and which place are you considering?", "स्थान परिवर्तन काम, परिवार या जीवनशैली के लिए है, और किस जगह का विचार है?", "Move work, family ya lifestyle ke liye hai, aur kaunsi jagah sochi hai?"),
    "move_plan": ("preferences", "relocation_plan", "What work, visa, housing, and budget arrangements are already in place?", "काम, वीज़ा, घर और बजट की कौन सी व्यवस्था हो चुकी है?", "Work, visa, housing aur budget ki kya taiyari hai?"),
    "property_goal": ("preferences", "property_goal", "Is this your first home, a replacement home, or an investment property?", "यह पहला घर, घर बदलना या निवेश की संपत्ति है?", "Yeh first home, replacement ya investment property hai?"),
    "financing": ("money", "property_financing", "What down payment and affordable monthly repayment have you planned?", "डाउन पेमेंट और वहनीय मासिक किस्त की क्या योजना है?", "Down payment aur affordable monthly EMI ki kya planning hai?"),
    "partner": ("relationships", "marriage_goal", "Are you asking about readiness generally, or marriage with a particular partner?", "आप सामान्य तैयारी के बारे में पूछ रहे हैं या किसी खास साथी से विवाह के बारे में?", "General readiness pooch rahe hain ya kisi specific partner ke saath shaadi?"),
    "constraints": ("relationships", "marriage_constraints", "What matters most to you, and what concerns or responsibilities affect this decision?", "आपके लिए सबसे जरूरी क्या है, और कौन सी चिंता या जिम्मेदारी इस निर्णय को प्रभावित करती है?", "Aapke liye kya zaroori hai, aur kaunsi concern ya zimmedari decision ko affect karti hai?"),
    "investment_goal": ("money", "investment_goal", "What is the investment for, and when would you need the money?", "निवेश का उद्देश्य क्या है, और धन कब चाहिए होगा?", "Investment ka goal kya hai, aur paisa kab chahiye?"),
    "investment_risk": ("money", "investment_constraints", "Which options are you comparing, and what loss could you absorb after essential expenses and emergency savings?", "किन विकल्पों की तुलना कर रहे हैं, और जरूरी खर्च व आपात बचत के बाद कितना नुकसान सह सकते हैं?", "Kaunse options hain, aur essential expenses aur emergency savings ke baad kitna loss manage kar sakte hain?"),
    # Caught live: "main shaadi se dukhi hoon" (a distress statement, not a
    # neutral status check) got the exact same "your relationships may have
    # good and hard moments" reading anyone would — a real astrologer asks
    # what's actually happening before reaching for the chart. Reuses the
    # SAME DECISION_SLOTS mechanism the 6 decisions already use to ask a
    # material question before answering, not a separate "problem mode."
    "concern_type": (
        "relationships", "concern_type",
        "What's the concern — communication, frequent arguments, emotional distance, trust, or family "
        "interference? And how long has this been going on?",
        "चिंता किस बारे में है — बातचीत, बार-बार झगड़े, भावनात्मक दूरी, भरोसा, या पारिवारिक हस्तक्षेप? और यह कब से चल रहा है?",
        "Concern kis baare mein hai — communication, baar baar arguments, emotional distance, trust, ya family "
        "interference? Aur yeh kab se chal raha hai?",
    ),
}
DECISION_SLOTS = {
    "job_change_decision": ("reason", "offer", "runway"),
    "business_start_decision": ("business_goal", "funding"),
    "relocation_decision": ("move_goal", "move_plan"),
    "house_purchase_decision": ("property_goal", "financing"),
    "marriage_decision": ("partner", "constraints"),
    "investment_decision": ("investment_goal", "investment_risk"),
    "relationship_conflict": ("concern_type",),
}


# --- Intent menus ------------------------------------------------------
# A numbered menu of genuinely different things a bare, ambiguous topic ask
# could mean — resolved to one of several ALREADY-EXISTING categories by the
# user's own numbered pick, personalized with known facts where available
# (the spouse's actual name, for instance). Distinct from QUESTIONS/
# DECISION_SLOTS above, which collect FACTS for a category already chosen;
# this instead helps CHOOSE the category itself. Reserved for the 3
# highest-ambiguity asks (relationship/career/week) where a wrong-angle
# answer feels the most generically wrong — confirmed live across several
# real transcripts, not applied broadly to every topic (most topics — health,
# education, friends — don't have this many genuinely different angles).
# Gated once per conversation (a sticky "<gate>_clarified" flag, same
# convention as every other clarifying gate in this module): once answered,
# a later ask on the same topic gets a real answer, not the menu again.
def _marriage_menu(facts, language):
    relationships, family = facts.get("relationships", {}), facts.get("family", {})
    spouse = relationships.get("spouse_name", {}).get("value")
    spouse_title = spouse.title() if spouse else None
    options = [(
        "spouse_relationship",
        f"Your bonding and understanding with {spouse_title}" if spouse_title else "Your bonding and understanding with your partner",
        f"{spouse_title} के साथ आपकी समझ और जुड़ाव" if spouse_title else "अपने साथी के साथ आपकी समझ और जुड़ाव",
        f"{spouse_title} ke saath aapki understanding aur bonding" if spouse_title else "Apne partner ke saath aapki understanding aur bonding",
    ), (
        "relationship_conflict",
        "A current relationship concern",
        "किसी मौजूदा रिश्ते की चिंता",
        "Koi current relationship concern",
    )]
    if "planning_intent" in family:
        options.append((
            "family_planning", "Family planning", "पारिवारिक योजना", "Family planning",
        ))
    options.append((
        "marriage", "Your overall married life going forward", "आगे आपका समग्र वैवाहिक जीवन", "Aage aapki overall married life",
    ))
    lead = choose(
        language,
        "You mentioned you're already married, so I won't treat this as marriage timing. Which of these would "
        "you like to focus on? Reply with a number:",
        "आपने बताया था कि आप विवाहित हैं, इसलिए मैं इसे विवाह के समय के रूप में नहीं देखूंगा। इनमें से आप किस पर ध्यान "
        "देना चाहते हैं? नंबर के साथ जवाब दें:",
        "Aapne bataya tha ki aap married hain, isliye main isko marriage timing ke roop mein nahi dekhunga. "
        "Inme se kis par focus karna chahte hain? Number ke saath jawab dein:",
    )
    return lead, options


def _career_menu(language):
    options = [
        ("career", "Growth in your current path", "अपनी मौजूदा राह में विकास", "Apni current path mein growth"),
        ("job_change_decision", "Changing your job", "अपनी नौकरी बदलना", "Apni job badalna"),
        ("career_promotion_timing", "Promotion timing", "पदोन्नति का समय", "Promotion ka time"),
        ("business_start_decision", "Starting a business", "व्यवसाय शुरू करना", "Business shuru karna"),
    ]
    lead = choose(
        language,
        "To understand your career, I need to know what you'd like to focus on. Reply with a number:",
        "आपके करियर को समझने के लिए मुझे यह जानना होगा कि आप किस पर ध्यान देना चाहते हैं। नंबर के साथ जवाब दें:",
        "Aapke career ko samajhne ke liye yeh jaanna hoga ki aap kis par focus karna chahte hain. Number ke "
        "saath jawab dein:",
    )
    return lead, options


def _week_menu(language):
    options = [
        ("career", "Career/work", "करियर/काम", "Career/kaam"),
        ("money", "Money", "पैसा", "Paisa"),
        ("marriage", "Relationship", "रिश्ता", "Relationship"),
        ("family", "Family", "परिवार", "Family"),
        ("health", "Health/routine", "सेहत/दिनचर्या", "Health/routine"),
        ("week_ahead", "Overall week", "पूरा हफ्ता", "Overall week"),
    ]
    lead = choose(
        language,
        "Which area would you like to see this week through? Reply with a number, or tell me the specific "
        "situation:",
        "इस हफ्ते को आप किस क्षेत्र के नज़रिए से देखना चाहते हैं? नंबर के साथ जवाब दें, या अपनी स्थिति बताएं:",
        "Is hafte ko aap kis area ke nazariye se dekhna chahte hain? Number ke saath jawab dein, ya apni "
        "situation batayein:",
    )
    return lead, options


def _format_menu(lead, options, language):
    lines = [choose(language, en, hi, hgl) for _, en, hi, hgl in options]
    body = "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1))
    return f"{lead}\n\n{body}"


async def load_state(db, user_id, rishi_id):
    row = await db.scalar(select(ConversationState).where(
        ConversationState.user_id == user_id, ConversationState.rishi_id == (rishi_id or "")))
    return row, dict(row.data) if row else {}


async def save_state(db, user_id, rishi_id, data):
    row, _ = await load_state(db, user_id, rishi_id)
    if row is None:
        row = ConversationState(user_id=user_id, rishi_id=rishi_id or "", data=data)
        db.add(row)
    else:
        row.data = data
    await db.flush()


def resume(understanding, message, state, language):
    """Bind only a follow-up answer to a pending slot; new questions switch topic."""
    pending = state.get("pending", [])
    direct = detect_intents(message)
    is_new_question = is_question(message)
    numbered_answer = bool(re.match(r"\s*1[.)]", message))
    switched_topic = direct and not numbered_answer and not set(direct).intersection(state.get("categories", []))

    # Two more short-reply bindings, both caught live off a real transcript
    # where they fell through to the generic clarifying question instead —
    # checked before the DECISION_SLOTS branch below since a bare "kaam"/
    # "no" would otherwise just fail `pending`'s own numbered-answer parsing.
    if state.get("pending_situation_check") and not direct and not is_new_question:
        if message_is_negative_reply(message) or message.strip().startswith(("नहीं", "no")):
            # Nothing changed — acknowledge and move on, never re-ask.
            understanding.needs_clarification = False
            understanding.clarifying_question = None
            state["pending_situation_check"] = None
            state["pending_domain_clarification"] = False
            return understanding
        if message_is_affirmative_reply(message) or message.strip().startswith(("हाँ", "हां")):
            understanding.needs_clarification = True
            understanding.clarifying_question = choose(
                language,
                "What's changed? Tell me and I'll use that instead.",
                "क्या बदला है? बताइए, मैं उसी के अनुसार जवाब दूंगा/दूंगी।",
                "Kya badla hai? Bata dijiye, main usi hisaab se jawab dunga.",
            )
            state["pending_situation_check"] = None
            # This is now a free-text "what changed?" answer expected next,
            # not a domain-word one — extract_knowledge handles a free-text
            # reply on its own; no special binding needed for it.
            state["pending_domain_clarification"] = False
            return understanding
    if state.get("pending_domain_clarification") and not direct and not is_new_question:
        resolved = _resolve_domain_word(message)
        if resolved:
            understanding.categories = [resolved]
            understanding.needs_clarification = False
            understanding.clarifying_question = None
            state["pending_domain_clarification"] = False
            state["categories"] = understanding.categories
            return understanding

    # A pending intent-menu answer (see questions_for's marriage/career/week
    # gates below) resolves three ways: a bare number picks that option
    # directly; a free-text reply that itself resolves to a real category
    # (e.g. "family planning") is honored via the SAME switched_topic
    # mechanism below rather than special-cased here; anything else falls
    # back to the plain base category the menu was offering angles on.
    # Either way this counts as answered — the sticky "<gate>_clarified"
    # flag means a later ask on the same topic gets a real answer, not the
    # menu again.
    menu = state.get("pending_intent_menu")
    if menu:
        numbered_pick = re.match(r"\s*([1-9])\b", message.strip())
        if numbered_pick and int(numbered_pick[1]) - 1 < len(menu["options"]):
            understanding.categories = [menu["options"][int(numbered_pick[1]) - 1]]
            understanding.needs_clarification = False
            understanding.clarifying_question = None
            state["pending_intent_menu"] = None
            state[f"{menu['gate']}_clarified"] = True
            state["categories"] = understanding.categories
            return understanding
        state["pending_intent_menu"] = None
        state[f"{menu['gate']}_clarified"] = True
        if not direct:
            # No number, and the free text itself doesn't resolve to
            # anything specific either — fall back to the plain base topic
            # rather than re-showing the same menu or getting stuck.
            understanding.categories = [menu["base_category"]]
            understanding.needs_clarification = False
            understanding.clarifying_question = None
            state["categories"] = understanding.categories
            return understanding
        # A real free-text category IS present — let the normal
        # switched_topic handling below route to it.

    if pending and not is_new_question and not switched_topic:
        numbered = dict(re.findall(r"(?:^|\n|;|\s)([1-3])[.)]\s*(.*?)(?=(?:\s[1-3][.)])|\n|;|$)", message))
        # Multiple answers require numbering or explicit extractable facts;
        # never copy one ambiguous sentence into three unrelated fact slots.
        for i, slot in enumerate(pending, 1):
            value = numbered.get(str(i)) or (message if len(pending) == 1 else None)
            if value and len(value.strip()) > 1:
                domain, key = QUESTIONS[slot][:2]
                understanding.context_updates.append(ContextUpdate(domain, key, value.strip()[:240], "high", "user_stated"))
        # A contextual short answer can be routed even before every slot is filled.
        understanding.categories = state.get("categories", direct)
        understanding.needs_clarification = False
        understanding.clarifying_question = None
        state["pending"] = []
    elif (
        not direct and not is_new_question and state.get("categories")
        and (
            re.search(r"\b(?:that|then|it|same|aur|phir)\b", message.lower())
            # Caught live: "fights" — one word, ALSO one of the concern_type
            # question's own offered options — sent as a fresh message (no
            # slot left pending, since it had already been answered once
            # this conversation) fell through every branch above and landed
            # on the fully generic "what do you want to talk about" reply,
            # discarding a still-obviously-relevant topic for no reason
            # other than the message being short and containing none of the
            # specific continuation words above. A short reply with no
            # independent topic signal of its own defaults to "still talking
            # about the same thing" rather than "conversation over, start
            # fresh" — state["categories"] has no expiry, so this holds for
            # as long as the conversation's own row does, not just one turn.
            or len(message.split()) <= 4
        )
    ):
        understanding.categories = state["categories"]
        understanding.needs_clarification = False
        understanding.clarifying_question = None
    elif direct and (is_new_question or switched_topic):
        state["pending"] = []
        if direct != state.get("categories"):
            state["asked"] = []
    if understanding.categories:
        state["categories"] = understanding.categories
    # Nothing above resolved this turn either — remember to try binding a
    # short domain-word reply on the NEXT turn (see the branch above).
    # Cleared the moment anything real is understood, so a stale flag can
    # never misfire against an unrelated later message.
    state["pending_domain_clarification"] = bool(understanding.needs_clarification)
    return understanding


def known_slot(slot, facts):
    domain, key = QUESTIONS[slot][:2]
    available = facts.get(domain, {})
    if key in available and available[key].get("confidence") != "low":
        return True
    aliases = {
        "reason": ("main_concern", "top_goal"),
        "runway": ("savings_duration", "income_plan"),
        "funding": ("funding_plan",),
        "business_goal": ("business_type", "stage"),
        "offer": ("job_offer", "transition_intent"),
        "financing": ("down_payment", "budget"),
    }
    return any(k in available and available[k].get("confidence") != "low" for k in aliases.get(slot, ()))


def questions_for(categories, facts, life_state, state, language):
    # Intent-menu gates checked first (relationship/career/week — the 3
    # highest-ambiguity asks, see the module docstring above _marriage_menu).
    # Widened from "marriage_timing" only: a bare "tell me about my
    # relationship" resolved to the plain "marriage" category used to hit
    # neither this gate nor marriage_timing's, so a married user got the
    # exact same single-person house-7 read someone still looking for a
    # partner would — confirmed live as the real gap behind the failing
    # transcript. Sub-intents (spouse_relationship, family_planning, etc.)
    # are already disambiguated by detect_intents() and skip this question
    # entirely, same as marriage_decision already did.
    if (
        ("marriage_timing" in categories or "marriage" in categories)
        and life_state.get("marital_status") == "married"
        and not state.get("marriage_clarified")
    ):
        lead, options = _marriage_menu(facts, language)
        state["pending_intent_menu"] = {"gate": "marriage", "base_category": "marriage", "options": [o[0] for o in options]}
        state["pending"] = []
        return _format_menu(lead, options, language)
    # A bare "career" ask with genuinely nothing known yet (no occupation,
    # no business, no employment state) — caught live giving the exact same
    # generic answer regardless of whether the person is a student, employed,
    # or running a business. Skipped once anything at all is known, and
    # never re-asked after the first time this conversation.
    career_known = (
        "occupation" in facts.get("career", {}) or "business_type" in facts.get("business", {})
        or life_state.get("career_state") or life_state.get("business_state") not in (None, "none")
    )
    if "career" in categories and not career_known and not state.get("career_clarified"):
        lead, options = _career_menu(language)
        state["pending_intent_menu"] = {"gate": "career", "base_category": "career", "options": [o[0] for o in options]}
        state["pending"] = []
        return _format_menu(lead, options, language)
    # "Mera hafta kaisa rahega?" reused the SAME single daily reading no
    # matter what area was actually meant — caught live giving a generic
    # answer with no real weekly engine behind it (see templates.py's
    # week_ahead comment). Asked once per conversation; a specific area
    # mentioned in a LATER week question is handled by normal category
    # detection, not re-gated here.
    if "week_ahead" in categories and not state.get("week_clarified"):
        lead, options = _week_menu(language)
        state["pending_intent_menu"] = {"gate": "week", "base_category": "week_ahead", "options": [o[0] for o in options]}
        state["pending"] = []
        return _format_menu(lead, options, language)

    slots = []
    for category in categories:
        slots.extend(s for s in DECISION_SLOTS.get(category, ()) if not known_slot(s, facts))
    asked = set(state.get("asked", []))
    slots = list(dict.fromkeys(s for s in slots if s not in asked))[:3]
    state["pending"] = slots
    state["asked"] = list(asked | set(slots))
    if not slots:
        return None
    lines = [choose(language, *QUESTIONS[s][2:]) for s in slots]
    if len(lines) == 1:
        return lines[0]
    lead = choose(language, "These details would change the advice. You can answer by number:", "इन बातों से सलाह बदलेगी। आप क्रमांक के अनुसार उत्तर दे सकते हैं:", "In details se advice badlegi. Aap number ke hisaab se jawab de sakte hain:")
    return lead + "\n\n" + "\n".join(f"{i}. {q}" for i, q in enumerate(lines, 1))
