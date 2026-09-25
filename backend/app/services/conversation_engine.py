"""Persistent intent resolution and decision-critical questions. No provider calls."""
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models.conversation_state import ConversationState
from app.services.chat_understanding import ContextUpdate
from app.services.native_understanding import (
    choose, detect_intents, extract_bare_suitability_query, is_navigational_reply, is_question,
)
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
    # "work" — caught live: the generic clarifying question itself literally
    # offers "work" as one of its five option words ("work, relationships,
    # money, business, or family?"), but replying with that exact word
    # wasn't recognized here, so it fell through to the branches below
    # instead of ever resolving to career.
    "career": ("kaam", "job", "naukri", "career", "work", "काम", "नौकरी", "करियर"),
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


# Phrases that signal a DELIBERATE topic change even in a short message —
# checked before the pending-answer heuristic below overrides a fresh
# category match, so a genuine "let's talk about marriage instead" is never
# swallowed as an answer to an unrelated pending business/career question.
_NEW_TOPIC_MARKERS = (
    "instead", "actually", "forget that", "forget it", "never mind", "nevermind",
    "what about", "let's talk about", "lets talk about", "i want to talk about",
    "can you tell me about", "tell me about", "i want to know about",
    "भूल जाओ", "बात करते हैं",
)


# Caught live: a bare "yes" answering "What would you sell, and have you
# tested demand with customers?" got bound verbatim as business.goal="yes"
# — a content-free acknowledgement accepted as if it named an actual
# business type. Most DECISION_SLOTS questions are open-ended, where a bare
# acknowledgement can never be a genuine answer — but a few ("contacts":
# "Do you already have suppliers or potential customers?") are genuinely
# yes/no-answerable, and a bare "yes"/"no" IS a real, complete answer to
# those specifically (caught live in the OTHER direction too: rejecting a
# real "no" there and re-asking the same yes/no question forever is exactly
# the "no reset to a bare acknowledgement" failure this guards against, just
# from the opposite side). Checked against this allowlist below, not applied
# blanket to every pending slot.
_NON_SUBSTANTIVE_REPLIES = {
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "fine", "alright",
    "no", "nope", "nah", "haan", "han", "nahi", "nahin", "हाँ", "हां", "नहीं",
}
_YES_NO_ANSWERABLE_SLOTS = {"contacts"}


def _is_substantive_answer(value: str, slot: str | None = None) -> bool:
    if slot in _YES_NO_ANSWERABLE_SLOTS:
        return True
    return value.strip().lower().strip(" .!?") not in _NON_SUBSTANTIVE_REPLIES


def _looks_like_pending_answer(message: str, is_new_question: bool) -> bool:
    """Caught live: a short, plain-text answer to a pending slot's own
    question (e.g. "Yes, alongside my job" answering transition_mode's
    "alongside your job or full-time?") got read as switching topic to
    "career" purely because it contains the word "job" — an incidental
    keyword match `detect_intents` has no way to tell apart from a real new
    topic. A pending question's answer takes priority over a fresh category
    match unless the message is itself a genuine new question or explicitly
    signals a topic change — this is the deterministic floor for that;
    chat_gpt_mediator.assess_and_generate_question's own is_confirmation
    judgment can additionally corroborate it when that layer is enabled, but
    must never be required for this to work."""
    if is_new_question:
        return False
    text = message.strip().lower()
    if any(marker in text for marker in _NEW_TOPIC_MARKERS):
        return False
    if message_is_affirmative_reply(message) or message_is_negative_reply(message):
        return True
    return len(text.split()) <= 8


def _resolve_domain_word(message: str) -> str | None:
    text = message.strip().lower()
    for category, words in _DOMAIN_WORDS.items():
        if any(text == w or text.startswith(w + " ") for w in words):
            return category
    return None

# Stable slot IDs decouple answer storage from translated question wording.
# A slot is asked only for decisions where its answer changes practical framing.
QUESTIONS = {
    "market": ("business", "target_market", "Which city or market would you serve?", "आप किस शहर या बाजार में काम करेंगे?", "Kaunse city ya market mein kaam karenge?"),
    "contacts": ("business", "customer_supplier_contacts", "Do you already have suppliers or potential customers?", "क्या आपके पास आपूर्तिकर्ता या संभावित ग्राहक हैं?", "Kya suppliers ya potential customers pehle se hain?"),
    "transition_mode": ("business", "transition_mode", "Would you start alongside your job or move into it full-time?", "क्या नौकरी के साथ शुरू करेंगे या पूरा समय व्यवसाय करेंगे?", "Job ke saath shuru karenge ya full-time business?"),
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
    # concern_type above is set via _relationship_concern_menu's numbered pick
    # now, not asked as a free-text DECISION_SLOTS question — see
    # DECISION_SLOTS["relationship_conflict"] below, which only lists these
    # two follow-ups. The fact key/domain stays identical either way, so
    # _relationship_concern_sentence (templates.py) needs no changes.
    "concern_pattern": (
        "relationships", "concern_pattern",
        "Does this tend to happen around one specific recurring topic, or is it more general day-to-day "
        "tension? And after a disagreement, does it usually resolve quickly, cause distance, or stay "
        "unresolved for a while?",
        "क्या यह किसी एक खास विषय पर बार-बार होता है, या यह सामान्य रोज़मर्रा का तनाव है? और असहमति के बाद, क्या यह जल्दी "
        "सुलझ जाता है, दूरी बढ़ती है, या कुछ समय तक अनसुलझा रहता है?",
        "Kya yeh kisi ek specific topic par baar baar hota hai, ya general roz ka tension hai? Aur disagreement "
        "ke baad, jaldi sulajh jata hai, distance badh jata hai, ya kuch time tak unresolved rehta hai?",
    ),
    "concern_goal": (
        "relationships", "concern_goal",
        "What would help most right now — working on this together, understanding why it keeps happening, "
        "or getting a sense of how this phase plays out?",
        "अभी सबसे ज़्यादा मददगार क्या होगा — साथ मिलकर इस पर काम करना, यह समझना कि ऐसा बार-बार क्यों होता है, या यह जानना "
        "कि यह दौर आगे कैसा रहेगा?",
        "Abhi sabse zyada helpful kya hoga — saath milkar isपर kaam karna, yeh samajhna ki baar baar kyun hota "
        "hai, ya yeh jaanna ki yeh phase aage kaisa rahega?",
    ),
    # career_confusion — caught live: "I am not sure about my career" went
    # straight to a generic chart reading with zero context, the same class
    # of gap relationship_conflict's concern_type already closed for
    # relationships. "career_direction"'s key (transition_intent) and
    # "career_problem"'s alias (change_reason) deliberately reuse the SAME
    # fact keys job_change_decision's reason/offer slots already read/write,
    # so answering one flow never asks the other to repeat itself.
    "career_problem": (
        "career", "main_concern",
        "What's actually bothering you about your career right now — growth, money, lack of interest, work "
        "pressure, or something else?",
        "आपके करियर को लेकर सबसे ज़्यादा परेशानी किस बात की है — विकास, पैसा, रुचि की कमी, काम का दबाव, या कुछ और?",
        "Aapke career ko lekar sabse zyada pareshani kis baat ki hai — growth, paisa, interest ki kami, work "
        "pressure, ya kuch aur?",
    ),
    "career_direction": (
        "career", "transition_intent",
        "Do you want to stay in a job — maybe a different role or field — or are you thinking about moving "
        "to business or independent work instead?",
        "क्या आप नौकरी में ही रहना चाहते हैं — शायद किसी अलग भूमिका या क्षेत्र में — या व्यवसाय/स्वतंत्र काम की ओर बढ़ने के "
        "बारे में सोच रहे हैं?",
        "Kya aap job mein hi rehna chahte hain — shayad kisi alag role ya field mein — ya business/independent "
        "kaam ki taraf badhne ke baare mein soch rahe hain?",
    ),
}
DECISION_SLOTS = {
    "job_change_decision": ("reason", "offer", "runway"),
    "business_start_decision": ("business_goal", "funding", "contacts", "market", "transition_mode"),
    "relocation_decision": ("move_goal", "move_plan"),
    "house_purchase_decision": ("property_goal", "financing"),
    "marriage_decision": ("partner", "constraints"),
    "investment_decision": ("investment_goal", "investment_risk"),
    "relationship_conflict": ("concern_pattern", "concern_goal"),
    "career_confusion": ("career_problem", "career_direction"),
    # Bare "business" (e.g. "I want to switch to business" mid a career
    # conversation, which resolves to categories ["business", "career"], not
    # the explicit-decision-phrased "business_start_decision") — caught
    # live: this had no DECISION_SLOTS entry at all, so it skipped straight
    # to an answer instead of asking what business_start_decision's own
    # business_goal/funding questions already ask for that flow. Reuses the
    # SAME two slots rather than inventing new question text.
    "business": ("business_goal", "funding"),
    # Deliberately NOT a DECISION_SLOTS entry here (unlike every other
    # decision category): "will clothing business work for me" is itself a
    # hypothetical "should I" style ask, not a first-person factual
    # assertion (native_understanding.extract_knowledge correctly never
    # stores a fact for it) — but the business TYPE it names is still real,
    # useful information for THIS turn's answer. chat.py re-extracts it
    # fresh from the current message every time (native_understanding.
    # extract_business_category_query) rather than routing through a
    # DECISION_SLOTS question that would otherwise wrongly re-ask "what
    # would you sell" even when the message just named it inline.
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


def _money_menu(language):
    """Same philosophy as _career_menu/_marriage_menu above, applied to
    money — a bare "money"/"paisa" mention with nothing yet known could mean
    genuinely different things, and guessing gets it wrong at least as often
    as career does. Each option routes to a real, already-built category
    (wealth_timing/investment_decision/business/financial_stability), not a
    new one — this only ever chooses AMONG existing engines."""
    options = [
        ("wealth_timing", "Income growth", "आय में वृद्धि", "Income mein growth"),
        ("investment_decision", "Savings or investment", "बचत या निवेश", "Savings ya investment"),
        ("business", "Business income", "व्यवसाय से आय", "Business se income"),
        ("financial_stability", "Expenses or financial pressure", "खर्च या आर्थिक दबाव", "Kharche ya financial pressure"),
        ("money", "Overall wealth building", "समग्र धन-निर्माण", "Overall wealth building"),
    ]
    lead = choose(
        language,
        "To understand your finances, I need to know what you'd like to focus on. Reply with a number:",
        "आपकी वित्तीय स्थिति को समझने के लिए मुझे यह जानना होगा कि आप किस पर ध्यान देना चाहते हैं। नंबर के साथ जवाब दें:",
        "Aapki finances samajhne ke liye yeh jaanna hoga ki aap kis par focus karna chahte hain. Number ke "
        "saath jawab dein:",
    )
    return lead, options


def _family_menu(language):
    """Same philosophy as _career_menu/_marriage_menu/_money_menu above,
    applied to family — "parents/home/responsibilities generally" routes to
    the bare "family" category itself (house 4's own generic reading), same
    convention as _career_menu's option 1 routing back to plain "career"."""
    options = [
        ("marriage", "Married life", "वैवाहिक जीवन", "Married life"),
        ("family_planning", "Children or family planning", "संतान या पारिवारिक योजना", "Children ya family planning"),
        ("family", "Parents, home, or family responsibilities", "माता-पिता, घर या पारिवारिक जिम्मेदारियां", "Parents, ghar ya family responsibilities"),
    ]
    lead = choose(
        language,
        "To understand your family situation, I need to know what you'd like to focus on. Reply with a number:",
        "आपकी पारिवारिक स्थिति को समझने के लिए मुझे यह जानना होगा कि आप किस पर ध्यान देना चाहते हैं। नंबर के साथ जवाब दें:",
        "Aapki family situation samajhne ke liye yeh jaanna hoga ki aap kis par focus karna chahte hain. Number "
        "ke saath jawab dein:",
    )
    return lead, options


def _relationship_concern_menu(language):
    """A numbered pick for relationship_conflict's concern_type fact — unlike
    _marriage_menu/_career_menu/_week_menu above, a pick here sets a FACT
    VALUE (relationships.concern_type), not a category switch, so it's
    resolved by its own state key (pending_concern_menu) in resume() rather
    than reusing pending_intent_menu's category-switching handler. A
    free-text reply (not a bare number) is still honored verbatim, exactly
    like the old single free-text question this replaces."""
    options = [
        ("frequent fights or arguments", "Frequent fights or arguments", "बार-बार झगड़े या बहस", "Baar baar fights ya arguments"),
        ("communication problems", "Communication problems", "बातचीत की समस्या", "Communication ki problem"),
        ("trust issues", "Trust issues", "भरोसे की कमी", "Trust ki kami"),
        ("emotional distance", "Emotional distance", "भावनात्मक दूरी", "Emotional distance"),
        ("family interference", "Family interference", "पारिवारिक हस्तक्षेप", "Family ka interference"),
        ("something else", "Something else", "कुछ और", "Kuch aur"),
    ]
    lead = choose(
        language,
        "What's the main concern? Reply with a number, or describe it in your own words:",
        "मुख्य चिंता क्या है? नंबर के साथ जवाब दें, या अपने शब्दों में बताएं:",
        "Main concern kya hai? Number ke saath jawab dein, ya apne shabdon mein bataayein:",
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
    # A GPT-generated question (chat_gpt_mediator.assess_and_generate_
    # question) targeting a concept outside the QUESTIONS catalogue — chat.py
    # sets this (and clears `pending`) instead of a slot id when the concept
    # is genuinely novel. Bound below exactly like a single pending slot,
    # just written to this domain/key directly instead of via QUESTIONS[slot].
    pending_dynamic = state.get("pending_dynamic")
    direct = detect_intents(message)
    # A business retraction (see native_understanding.extract_knowledge's
    # retractions list — e.g. "I don't have a business, it was just an
    # idea") fired THIS turn. Two things need clearing, not just one:
    # (1) any still-open business questions (business_goal, funding, ...)
    # are now asking about a business that no longer exists — left in
    # `pending`, the VERY NEXT bare topic word (e.g. a plain "career") gets
    # silently swallowed as a free-text answer to one of those stale
    # questions instead of being read as a topic change; (2) the
    # retraction message itself still mentions "business" as a plain word,
    # so `detect_intents` reads IT as a fresh business intent too (caught
    # live) — stripped from `direct` here, the same "no signal" treatment
    # the dasha weak-signal check below already gives a topic-agnostic
    # match, so every branch downstream that keys off `direct` sees this
    # turn the same way it would see a plain retraction with no business
    # word in it at all. Drops only the business-domain slots/categories,
    # so an unrelated pending question (e.g. mid a separate job-change
    # decision asked the same turn) is untouched.
    if any(domain == "business" for domain, _ in getattr(understanding, "retracted_facts", ())):
        # A stale business slot (business_goal/funding/...) is invalid
        # either way a business retraction happens — clear it regardless.
        pending = state["pending"] = [s for s in pending if QUESTIONS[s][0] != "business"]
        # Whether the CATEGORY itself is also cleared depends on WHICH
        # retraction this is, per correction 13 (personal-astrologer chat
        # upgrade plan) — "I don't have a business, it was just an idea"
        # abandons the idea entirely (business_state becomes "none", see
        # native_understanding.extract_knowledge) and should reset the
        # topic; "I changed my plan" retracts only the specific type/goal
        # WITHOUT touching business_state (still "considering") and must
        # stay ON the business topic so the very next question can ask what
        # actually changed, per chat.py's own naming-clarification hook —
        # clearing the category here would hide the stale value from
        # question_strategy.usable_facts' own category-relevance filtering
        # before that hook ever gets a chance to read it.
        abandoned_business = bool(understanding.life_state_update and understanding.life_state_update.business_state == "none")
        if abandoned_business:
            state["categories"] = [c for c in state.get("categories", []) if c not in ("business", "business_start_decision")]
            direct = [c for c in direct if c not in ("business", "business_start_decision")]
            # classify_message already set understanding.categories (from its
            # OWN, unfiltered detect_intents call) before resume() ever runs —
            # every branch below either overwrites it with the filtered
            # `direct`/`state["categories"]` or leaves it alone, and the final
            # `if understanding.categories: state["categories"] = understanding.
            # categories` line re-derives state from THIS value either way. Left
            # unfiltered here, that stale "business" would survive straight
            # through to the end even though every other path was just cleared.
            understanding.categories = [c for c in understanding.categories if c not in ("business", "business_start_decision")]
    # "dasha" is a bare, topic-agnostic "what period am I in?" meta-question
    # — detect_intents matches it on generic timing phrasing alone ("when
    # will be the right time?") with no domain word of its own. Caught
    # live, reproduced: asked right after establishing a business decision,
    # this reset the active topic to a generic dasha reading instead of
    # being understood as asking about THAT business's timing specifically
    # — and since `direct` was non-empty, it bypassed the "inherit the
    # active topic" handling below entirely. Treated as no signal (exactly
    # like an empty `direct`) whenever a DIFFERENT, more specific topic is
    # already active. Caught live again later: this originally fired for
    # ANY message matching detect_intents' generic dasha pattern, including
    # an EXPLICIT "What dasha am I running?" — a real, unambiguous dasha
    # question that must always win over a stale active topic, not just a
    # vague vague timing phrase with no domain word of its own. Narrowed to
    # the vague-phrasing case only (no literal "dasha"/"mahadasha"/
    # "antardasha" word in the message) — an explicit mention is always
    # treated as its own real topic, active or not.
    if (
        direct == ["dasha"] and not re.search(r"\b(?:maha|antar)?dasha\b", message.lower())
        and state.get("categories") and state["categories"] != ["dasha"]
    ):
        direct = []
    is_new_question = is_question(message)
    numbered_answer = bool(re.match(r"\s*1[.)]", message))
    # Caught live: answering business_start_decision's own pending slots
    # with "...I'll do this business parttime" got treated as SWITCHING
    # topic, because bare "business" (naturally mentioned while answering a
    # question ABOUT a business) doesn't string-match "business_start_
    # decision" exactly — derailing the whole pending-slot binding below
    # before it ever ran, on an answer that was never actually changing the
    # subject. Same category FAMILY (one name is a prefix of the other,
    # e.g. "business" / "business_start_decision") counts as staying on
    # topic, not switching away from it.
    same_family = any(
        d == s or s.startswith(d) or d.startswith(s)
        for d in direct for s in state.get("categories", [])
    )
    switched_topic = (
        direct and not numbered_answer and not same_family
        and not set(direct).intersection(state.get("categories", []))
        and not ((pending or pending_dynamic) and _looks_like_pending_answer(message, is_new_question))
    )

    # Two more short-reply bindings, both caught live off a real transcript
    # where they fell through to the generic clarifying question instead —
    # checked before the DECISION_SLOTS branch below since a bare "kaam"/
    # "no" would otherwise just fail `pending`'s own numbered-answer parsing.
    if state.get("pending_situation_check") and not direct and not is_new_question:
        situation_check = state["pending_situation_check"]
        if message_is_negative_reply(message) or message.strip().startswith(("नहीं", "no")):
            # Nothing changed — acknowledge and move on, never re-ask.
            understanding.needs_clarification = False
            understanding.clarifying_question = None
            # The general "stale fact" variant (see questions_for's
            # _stale_fact_gate, used for relationship concerns AND business
            # plans — the same risk class either way) needs one extra step
            # beyond the generic quote_id case: route THIS turn's answer to
            # the real category so the confirmed fact's actual content
            # renders instead of the generic reading that triggered this
            # check in the first place, and refresh the fact's
            # last_confirmed_at (via the normal upsert_fact "unchanged
            # value" path in chat.py) so it isn't asked about again for
            # another 24 hours.
            if isinstance(situation_check, dict) and situation_check.get("stale_fact"):
                sf = situation_check["stale_fact"]
                understanding.categories = [sf["route_category"]]
                understanding.context_updates.append(
                    ContextUpdate(sf["domain"], sf["key"], sf["value"], "high", "user_confirmed")
                )
                state["categories"] = understanding.categories
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
    # A pending relationship-concern menu answer (see questions_for's
    # relationship_conflict gate / _relationship_concern_menu above) — a bare
    # number picks the matching canned label; anything else is stored
    # verbatim, exactly like the old free-text concern_type question this
    # replaces. Checked (and unconditionally resolved) before the generic
    # domain-word fallback further below so a free-text concern that happens
    # to start with a domain word ("money"/"family"...) is never misread as
    # switching topic instead of answering the menu.
    concern_menu = state.get("pending_concern_menu")
    if concern_menu:
        numbered_pick = re.match(r"\s*([1-9])\b", message.strip())
        if numbered_pick and int(numbered_pick[1]) - 1 < len(concern_menu["options"]):
            value = concern_menu["options"][int(numbered_pick[1]) - 1]
        else:
            value = message.strip()
        if value:
            understanding.context_updates.append(
                ContextUpdate("relationships", "concern_type", value[:240], "high", "user_stated")
            )
        understanding.categories = state.get("categories") or ["relationship_conflict"]
        understanding.needs_clarification = False
        understanding.clarifying_question = None
        state["pending_concern_menu"] = None
        state["categories"] = understanding.categories
        return understanding

    # An explicit one-word domain name ("work", "paisa", "family"...) is a
    # strong, unambiguous signal and must always win over a stale topic
    # sitting in state["categories"] — never left to fall through into a
    # branch that merely guesses. Caught live: replying "work" to "what
    # should i do?" fell through every branch below (detect_intents("work")
    # finds nothing on its own, so this used to only ever get resolved when
    # state["pending_domain_clarification"] happened to be set at that exact
    # instant) into "reuse the last topic", which answered it with
    # married-life content left over from a much earlier, unrelated part of
    # the conversation. Tried unconditionally (not just while
    # pending_domain_clarification happens to be set) and checked after the
    # concern-menu above so an active menu always wins first.
    domain_word = _resolve_domain_word(message) if not direct and not is_new_question else None
    if domain_word:
        understanding.categories = [domain_word]
        understanding.needs_clarification = False
        understanding.clarifying_question = None
        state["pending_domain_clarification"] = False
        state["pending_intent_menu"] = None
        state["pending"] = []
        state["categories"] = understanding.categories
        return understanding
    if state.get("pending_domain_clarification") and not direct and not is_new_question:
        # domain_word just above already had its chance and failed. An
        # unresolved reply to "what do you want to talk about?" must not
        # silently fall through to the "reuse the last topic" branch further
        # below — caught live: replying "work" (before it was added to
        # _DOMAIN_WORDS above) fell through and got answered using a stale
        # topic (relationship_conflict/"fights") left over from a much
        # earlier, unrelated conversation, since state["categories"] has no
        # expiry and a short unresolved reply looks identical to that
        # branch's "short in-topic continuation" case. Re-ask instead of
        # ever guessing a topic the user hasn't actually named.
        understanding.needs_clarification = True
        understanding.clarifying_question = choose(
            language,
            "I didn't quite catch that — work, relationships, money, business, or family?",
            "मैं ठीक से समझ नहीं पाया — काम, रिश्ते, पैसा, व्यवसाय या परिवार?",
            "Samajh nahi paya — kaam, relationships, paisa, business ya family?",
        )
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

    if pending_dynamic and not pending and not is_new_question and not switched_topic:
        value = message.strip()
        if value and len(value) > 1:
            understanding.context_updates.append(
                ContextUpdate(pending_dynamic["domain"], pending_dynamic["key"], value[:240], "high", "user_stated")
            )
        understanding.categories = state.get("categories", direct)
        understanding.needs_clarification = False
        understanding.clarifying_question = None
        state["pending_dynamic"] = None
        return understanding

    if pending == ["business_goal"] and not switched_topic:
        # "Will clothing work for me?" answering "What would you sell?" is
        # BOTH naming the type AND asking a genuine business-category-
        # suitability question in one message — a real, reproduced live
        # case. Bind the named type as the answer (same fact key
        # business_goal's question always writes) AND route THIS reply to
        # the dedicated suitability capability instead of continuing to ask
        # for funding, per correction 18 (personal-astrologer chat upgrade
        # plan): the first substantive part of the answer must address what
        # was actually asked. Deliberately narrow — only fires while this
        # SPECIFIC slot is pending, never as a topic-agnostic pattern (see
        # extract_bare_suitability_query's own docstring).
        suitability_type = extract_bare_suitability_query(message)
        if suitability_type:
            domain, key = QUESTIONS["business_goal"][:2]
            understanding.context_updates.append(ContextUpdate(domain, key, suitability_type, "high", "user_stated"))
            understanding.categories = ["business_category_suitability"] + [
                c for c in state.get("categories", direct) if c != "business_category_suitability"
            ]
            understanding.needs_clarification = False
            understanding.clarifying_question = None
            state["pending"] = []
            state["categories"] = understanding.categories
            return understanding

    if pending and not is_new_question and not switched_topic and len(pending) == 1 and message.strip() and not _is_substantive_answer(message, pending[0]):
        # A bare "yes"/"no"/"ok" is never a real answer to any DECISION_
        # SLOTS question (none of them are yes/no questions) — re-ask the
        # SAME question rather than silently binding the acknowledgement as
        # if it named something real. Also drops this slot from `asked` —
        # otherwise chat.py's OWN separate questions_for() call later this
        # same request (which runs regardless of what resume() decided)
        # would see the slot as "already asked" and silently skip straight
        # to the NEXT one, so the very next turn's real answer would bind to
        # the wrong slot even though this one was genuinely never answered.
        state["asked"] = [s for s in state.get("asked", []) if s != pending[0]]
        understanding.categories = state.get("categories", direct)
        understanding.needs_clarification = True
        understanding.clarifying_question = choose(language, *QUESTIONS[pending[0]][2:])
        return understanding

    if pending and not is_new_question and not switched_topic:
        numbered = dict(re.findall(r"(?:^|\n|;|\s)([1-3])[.)]\s*(.*?)(?=(?:\s[1-3][.)])|\n|;|$)", message))
        # Real users very often type a numbered multi-part reply WITHOUT a
        # period/paren after the digit ("1 clothing and yes i have
        # customers, 2 i have some savings...") — caught live: the strict
        # form above found nothing, and since a bare, unlabeled sentence
        # only ever binds when there's exactly ONE pending slot (see below),
        # NOTHING got captured this way here either — leaving
        # native_understanding.extract_knowledge's own, unrelated regexes
        # to try to make sense of the raw multi-part sentence on their own,
        # which produced garbled facts (one regex's capture group running
        # straight through into the SECOND numbered item's text). Retried
        # with a looser split only when the strict form found nothing AND
        # every slot number this question actually asked for is present as
        # its own bare marker — an ordinary sentence with a stray digit
        # ("I have 2 kids") never satisfies that and is left alone.
        if not numbered and len(pending) > 1:
            loosely_numbered = dict(re.findall(r"(?:^|\s)([1-3])\s+(.*?)(?=(?:\s[1-3]\s)|$)", message))
            if all(str(i) in loosely_numbered for i in range(1, len(pending) + 1)):
                numbered = loosely_numbered
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
    elif not direct and state.get("categories"):
        # A message with NO independently-detected category at all, while a
        # topic is already active, defaults to continuing that topic rather
        # than resetting to the fully generic "what do you want to talk
        # about" fallback — explicit, direct instruction: a follow-up must
        # inherit the active topic and intent unless the user explicitly
        # changes it, and an explicit change is exactly what `direct` being
        # non-empty already means (a real category keyword was named). This
        # used to be gated to short messages / a fixed pronoun list ("that",
        # "same"...) only — caught live, reproduced, repeatedly: "can you
        # tell me time?", "what about timing?", "any solution?" (all
        # QUESTIONS, so the old `not is_new_question` guard excluded them
        # outright) and "Will clothing work for me or should I look for
        # some other options?" (a real sentence, well past the old ≤3-word
        # cap) ALL have zero independent category signal of their own and
        # ALL are unambiguous follow-ups on the active topic — length and
        # phrasing turned out not to be reliable signals either way; the
        # presence or absence of a named category is. state["categories"]
        # has no expiry, so this holds for as long as the conversation's
        # own row does, not just one turn.
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
        # career_confusion's own two slots share fact keys with
        # job_change_decision's reason/offer above — aliased both ways so
        # answering either flow first never makes the other re-ask.
        "career_problem": ("change_reason", "top_goal"),
        "career_direction": ("job_offer",),
    }
    return any(k in available and available[k].get("confidence") != "low" for k in aliases.get(slot, ()))


def _fact_is_stale(fact: dict, hours: int = 24) -> bool:
    """A much shorter, purpose-specific window than life_context_service's
    120-day Context Decay (effective_confidence), which is tuned for "is
    this fact still safe to lean on at all" — this is instead "is this
    still what's actively being discussed," matching your own stated 24-hour
    boundary for topic persistence earlier this session. Missing/unparseable
    timestamps are treated as stale (fail toward asking, never toward
    silently assuming)."""
    last_confirmed_at = fact.get("last_confirmed_at")
    if not last_confirmed_at:
        return True
    try:
        confirmed = datetime.fromisoformat(last_confirmed_at)
    except ValueError:
        return True
    if confirmed.tzinfo is None:
        confirmed = confirmed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - confirmed) > timedelta(hours=hours)


def _stale_fact(facts: dict, domain: str, key: str, hours: int = 24) -> dict | None:
    """The shared precondition for every "is this still current?" reconfirm
    gate below (relationship concern, business plan, ...) — a fact exists,
    has a value, and hasn't been reconfirmed in `hours`. None otherwise
    (nothing to reconfirm): either unknown, or recent enough that asking
    again would itself be the annoying behavior."""
    fact = (facts.get(domain) or {}).get(key)
    if fact and fact.get("value") and _fact_is_stale(fact, hours):
        return fact
    return None


def questions_for(categories, facts, life_state, state, language, message=""):
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
    # marriage_clarified above never expires (ConversationState has no TTL),
    # so once a user has EVER picked an angle here, a bare "relationship"
    # mention any time later — even a stale concern_type fact from a much
    # earlier conversation — skips straight to the generic married-life
    # reading with that concern silently unused. Caught live, in your own
    # words: "is it the same or a different issue" was never asked. Only
    # fires for a STALE concern (see _fact_is_stale) — a concern answered
    # earlier in the SAME active exchange is handled by relationship_
    # conflict's own concern-menu/acknowledgment already, not this.
    # NOTE: a stale relationship-concern / business-plan reconfirm used to
    # live here (checking _stale_fact against relationships.concern_type
    # and business.goal). Removed — app.services.question_strategy.
    # relevance_question() (a separate, later-added module) already covers
    # this exact same "you previously mentioned X, is that still relevant?"
    # need, more completely, across career/marriage/money/family/business
    # uniformly, and runs BEFORE this function is even called (chat.py
    # skips questions_for() entirely whenever relevance_question() already
    # produced a prompt). Keeping both meant this gate and question_
    # strategy's own menu could BOTH fire back to back on consecutive turns
    # — caught live, reproduced: picking an option from question_strategy's
    # recall menu landed on a bare category, which then immediately hit
    # ANOTHER menu here, showing the user two clarifying menus in a row for
    # one simple mention.
    # A bare "career" ask with genuinely nothing known yet (no occupation,
    # no business, no employment state) — caught live giving the exact same
    # generic answer regardless of whether the person is a student, employed,
    # or running a business. Skipped once anything at all is known, and
    # never re-asked after the first time this conversation.
    career_known = (
        "occupation" in facts.get("career", {}) or "business_type" in facts.get("business", {})
        or life_state.get("career_state") or life_state.get("business_state") not in (None, "none")
    )
    # A co-occurring "business" category is itself already a specific,
    # disambiguated answer (detect_intents adds it whenever the message
    # names business/company/entrepreneur explicitly) — caught live: "I
    # want to switch to business" resolved to categories ["business",
    # "career"], but this gate only ever looked at career_known/facts, so
    # it fired anyway and re-asked "what do you want to focus on?" with
    # "starting a business" literally offered as one of the options the
    # user had just already picked in plain words.
    # Caught live, direct product feedback: a real, contentful question
    # ("How will we do financially?", "What about my career?") was getting
    # the SAME "which angle do you mean?" menu a bare, ambiguous one-word
    # mention ("career") genuinely needs — the astrology engine already has
    # everything it needs (the birth chart) to answer an outlook question
    # directly via the real house-based reading below; asking first when the
    # question is already answerable is exactly the "ask only when required"
    # violation this menu was never meant to cause. Gated to a genuinely
    # bare topic mention (is_navigational_reply's existing 1-2-word check,
    # already used elsewhere for exactly this "how ambiguous is this
    # message" judgment) — a real question always bypasses straight to a
    # direct answer instead.
    if (
        "career" in categories and "business" not in categories
        and "business_category_suitability" not in categories
        and not career_known and not state.get("career_clarified") and (not message or is_navigational_reply(message))
    ):
        lead, options = _career_menu(language)
        state["pending_intent_menu"] = {"gate": "career", "base_category": "career", "options": [o[0] for o in options]}
        state["pending"] = []
        return _format_menu(lead, options, language)
    # Same "career" philosophy applied to money — caught live: a bare
    # "money" ask with nothing known gave the exact same generic answer
    # regardless of whether the person meant income, savings, a business's
    # income, or financial pressure. Skipped once anything financial is
    # known, same convention as career_known above.
    money_known = bool(
        facts.get("money") or life_state.get("business_state") not in (None, "none")
    )
    if "money" in categories and not money_known and not state.get("money_clarified") and (not message or is_navigational_reply(message)):
        lead, options = _money_menu(language)
        state["pending_intent_menu"] = {"gate": "money", "base_category": "money", "options": [o[0] for o in options]}
        state["pending"] = []
        return _format_menu(lead, options, language)
    # Same "career" philosophy applied to family — caught live: a bare
    # "family" ask gave the same generic house-4 answer regardless of
    # whether the person meant married life, children, parents, or
    # responsibilities. Skipped once anything family-related is known.
    # Not life_state.children_count — that field defaults to 0 (not None)
    # even when genuinely unknown, so it can't distinguish "known: no kids"
    # from "never asked"; the structured fact store doesn't have that gap.
    family_known = bool(facts.get("family"))
    if "family" in categories and not family_known and not state.get("family_clarified") and (not message or is_navigational_reply(message)):
        lead, options = _family_menu(language)
        state["pending_intent_menu"] = {"gate": "family", "base_category": "family", "options": [o[0] for o in options]}
        state["pending"] = []
        return _format_menu(lead, options, language)
    # "Mera hafta kaisa rahega?" reused the SAME single daily reading no
    # matter what area was actually meant — caught live giving a generic
    # answer with no real weekly engine behind it (see templates.py's
    # week_ahead comment). Asked once per conversation; a specific area
    # mentioned in a LATER week question is handled by normal category
    # detection, not re-gated here.
    if "week_ahead" in categories and not state.get("week_clarified") and (not message or is_navigational_reply(message)):
        lead, options = _week_menu(language)
        state["pending_intent_menu"] = {"gate": "week", "base_category": "week_ahead", "options": [o[0] for o in options]}
        state["pending"] = []
        return _format_menu(lead, options, language)
    # relationship_conflict's concern_type — now a numbered pick (see
    # _relationship_concern_menu) instead of a free-text DECISION_SLOTS
    # question, so it's gated here alongside the other 3 intent-menus rather
    # than in the generic slots loop below. Skipped the instant concern_type
    # is known (same "never re-ask once known" rule every gate here follows)
    # — resolved via state["pending_concern_menu"] in resume(), not
    # pending_intent_menu, since a pick here sets a fact, not a category.
    if "relationship_conflict" in categories and not known_slot("concern_type", facts):
        lead, options = _relationship_concern_menu(language)
        state["pending_concern_menu"] = {"options": [o[0] for o in options]}
        state["pending"] = []
        return _format_menu(lead, options, language)

    slots = []
    for category in categories:
        slots.extend(s for s in DECISION_SLOTS.get(category, ()) if not known_slot(s, facts))
    asked = set(state.get("asked", []))
    # One question per turn, not up to 3 bundled into a single numbered
    # list — caught live, direct product feedback: dumping "1. What would
    # you sell... 2. How would you fund it... 3. Do you have suppliers..."
    # all at once read as a form, not a conversation. Capped to 1 here is
    # the whole fix: the single-slot branch right below already renders a
    # plain question with no numbering, and resume()'s slot-binding
    # (len(pending) == 1) already binds a bare, un-numbered answer straight
    # to it — both existed already for the "only 1 slot left" case, which
    # is now just every case. The next call naturally asks the next slot,
    # since `asked`/`known_slot` above already track what's been covered.
    candidates = list(dict.fromkeys(s for s in slots if s not in asked))
    # Stashed alongside the deterministic pick below (never replacing it) so
    # chat.py's OPTIONAL dynamic-question layer (chat_gpt_mediator.
    # choose_next_slot, gated behind chat_dynamic_questions_enabled) can pick
    # a DIFFERENT one of these SAME real candidates when more than one is
    # available — it can only choose among slots that already exist here,
    # never invent a new question. Every existing caller of this function
    # only reads state["pending"]/the return value, so this addition changes
    # nothing about current behavior.
    state["pending_candidates"] = candidates
    slots = candidates[:1]
    state["pending"] = slots
    state["asked"] = list(asked | set(slots))
    if not slots:
        return None
    return choose(language, *QUESTIONS[slots[0]][2:])
