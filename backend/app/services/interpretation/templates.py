"""Deterministic, rule-based interpreter — the fallback used whenever no LLM
API key is configured (or a live LLM call fails).

`period_analysis` and the brutal_truth/core_strength/core_challenge fields of
`complete_kundali` are hand-written per Dasha lord (not templated with a
single generic sentence) to give real variety and match the "commit, no
hedging, honest rating, memorable one-liner" tone without needing a live LLM
call — see app.services.interpretation.claude_interpreter for the prompt
these are standing in for. Everything else here stays intentionally simpler.
"""
import re
from typing import Any, Literal

from app.astro.constants import PLANET_NAMES_EN, PLANET_NAMES_HI, PlanetKey
from app.services.interpretation.base import Interpreter, Language, Mode


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _strip_trailing_stop(text: str) -> str:
    """Drops a trailing '.'/'।' so a hand-written standalone sentence (which
    ends with one) can be embedded mid-sentence without a stray full stop."""
    return text.rstrip("।.")


def _a_or_an(phrase: str) -> str:
    """English indefinite article for a phrase, e.g. "energetic and impatient"
    -> "an" (vowel sound), "mentally busy" -> "a"."""
    return "an" if phrase[:1].lower() in "aeiou" else "a"


# Hindi ordinals (oblique form, as used before "भाव" in "...भाव में/से/है")
# for houses 1-12. Unlike English, Hindi 1st is "पहले", not a numeral+suffix
# — writing "1वें भाव" (as a naive f"{n}वें भाव" would) is simply wrong Hindi,
# not just informal; this table is the one place that gets it right for
# every house so callers never reintroduce the "1वें" bug.
_HINDI_HOUSE_ORDINAL = {
    1: "पहले", 2: "दूसरे", 3: "तीसरे", 4: "चौथे", 5: "पांचवें", 6: "छठे",
    7: "सातवें", 8: "आठवें", 9: "नौवें", 10: "दसवें", 11: "ग्यारहवें", 12: "बारहवें",
}


def _hindi_house(n: int) -> str:
    """n -> "पांचवें भाव" etc. — always use this instead of hand-rolling
    f"{n}वें भाव" (see _HINDI_HOUSE_ORDINAL)."""
    return f"{_HINDI_HOUSE_ORDINAL[n]} भाव"

_TONE_BY_LORD_EN = {
    "Su": "steady but a little intense", "Mo": "emotionally sensitive", "Ma": "energetic and impatient",
    "Me": "mentally busy", "Ju": "optimistic and expansive", "Ve": "warm and easygoing",
    "Sa": "heavy but productive if you pace yourself", "Ra": "restless and a little unpredictable",
    "Ke": "introspective and low-key",
}
_TONE_BY_LORD_HI = {
    "Su": "स्थिर पर थोड़ा तीव्र", "Mo": "भावनात्मक रूप से संवेदनशील", "Ma": "ऊर्जावान पर अधीर",
    "Me": "मानसिक रूप से व्यस्त", "Ju": "आशावादी और विस्तृत", "Ve": "गर्मजोशी भरा और सहज",
    "Sa": "भारी पर सही गति से उत्पादक", "Ra": "बेचैन और थोड़ा अप्रत्याशित",
    "Ke": "आत्मनिरीक्षण करने वाला और शांत",
}

_FOCUS_BY_HOUSE_EN = {
    1: "yourself and your energy", 2: "money", 3: "communication", 4: "home and family",
    5: "creativity and romance", 6: "health and daily routine", 7: "relationships",
    8: "unexpected change", 9: "learning and travel", 10: "career", 11: "friendships and gains",
    12: "rest and letting go",
}
_FOCUS_BY_HOUSE_HI = {
    1: "खुद और अपनी ऊर्जा", 2: "धन", 3: "संवाद", 4: "घर और परिवार",
    5: "रचनात्मकता और प्रेम", 6: "स्वास्थ्य और दिनचर्या", 7: "रिश्तों",
    8: "अचानक बदलाव", 9: "सीखने और यात्रा", 10: "करियर", 11: "दोस्ती और लाभ",
    12: "आराम और छोड़ने",
}

# Qualitative read of a planet's classical dignity, reused across every
# house-lord placement sentence below — see app.astro.natal_insights.
_DIGNITY_QUALIFIER_EN = {
    "exalted": "operating unusually well from here",
    "debilitated": "under real strain from here",
    "own_sign": "comfortably placed, drawing on its natural strength",
    "neutral": "placed in an ordinary, unremarkable way",
}
_DIGNITY_QUALIFIER_HI = {
    "exalted": "यहां से असामान्य रूप से अच्छा असर दे रहा है",
    "debilitated": "यहां वास्तविक दबाव में है",
    "own_sign": "यहां सहज है और अपनी स्वाभाविक ताकत दिखा रहा है",
    "neutral": "यहां एक साधारण, सामान्य स्थिति में है",
}

# Per-lord period content: honest, specific, no hedging — the immediate
# (antardasha) lord drives risks/opportunities/one-liner; the mahadasha lord
# only sets the broader backdrop named in `theme`.
_PERIOD_CONTENT_EN: dict[str, dict[str, Any]] = {
    "Su": {
        "rating": 6,
        "risks": [
            "Friction with authority figures or bosses is likely if you push too hard for recognition.",
            "Overconfidence could make you dismiss advice you actually need.",
        ],
        "opportunities": [
            "A strong window to ask for what you've earned — promotions, credit, visibility.",
            "Good period to step into leadership rather than wait for permission.",
        ],
        "one_liner": "This period rewards standing up straighter, not staying quiet and hoping to be noticed.",
    },
    "Mo": {
        "rating": 6,
        "risks": [
            "Emotional decisions made in a low moment will look different in six months — wait them out.",
            "Family obligations may crowd out your own plans if you don't set limits.",
        ],
        "opportunities": [
            "A good window to repair a strained family relationship if you're willing to go first.",
            "Trust your instincts on home and domestic decisions — they're unusually reliable right now.",
        ],
        "one_liner": "Your feelings are loud this period — useful for connection, unreliable for major decisions.",
    },
    "Ma": {
        "rating": 5,
        "risks": [
            "Impatience will cost you more than the delay you're trying to avoid.",
            "Conflicts started now tend to escalate rather than resolve — pick your battles.",
        ],
        "opportunities": [
            "Real energy for anything that needs a decisive push — this isn't a period for waiting.",
            "Physical activity and competitive pursuits go well if channelled deliberately.",
        ],
        "one_liner": "This period hands you energy, not judgment — supply the judgment yourself.",
    },
    "Me": {
        "rating": 6,
        "risks": [
            "Words said quickly now are remembered longer than you'd like — reread before you send.",
            "Scattered attention across too many things will finish nothing well.",
        ],
        "opportunities": [
            "Contracts, negotiations, and paperwork move well if you stay organized.",
            "A strong period for learning something that pays off later, not just for entertainment.",
        ],
        "one_liner": "This is a period for finishing conversations, not starting five new ones.",
    },
    "Ju": {
        "rating": 8,
        "risks": [
            "Optimism can tip into overcommitting — check the numbers before you say yes.",
            "Growth without discipline just means a bigger mess to clean up later.",
        ],
        "opportunities": [
            "One of the more genuinely favourable periods for marriage, education, or financial growth.",
            "Good backing for taking a considered risk you've been sitting on.",
        ],
        "one_liner": "The door is open this period — the only real risk is walking through it carelessly.",
    },
    "Ve": {
        "rating": 7,
        "risks": [
            "Comfort can slide into complacency — this period won't push you, you have to push yourself.",
            "Overspending on comfort or appearances is the most likely way this period costs you.",
        ],
        "opportunities": [
            "Genuinely good window for relationships, creative work, and repairing what's been neglected.",
            "A good period to invest in your surroundings and relationships, not just endure them.",
        ],
        "one_liner": "This period is pleasant by default — don't mistake pleasant for productive.",
    },
    "Sa": {
        "rating": 5,
        "risks": [
            "Progress will be slower than you want, and pretending otherwise will only frustrate you.",
            "Isolation creeps in during Saturn periods — don't mistake it for a signal to withdraw completely.",
        ],
        "opportunities": [
            "What you build carefully now tends to actually last — Saturn punishes shortcuts, not effort.",
            "A legitimate period to get disciplined about something you've been avoiding.",
        ],
        "one_liner": "This period is a grind, not a disaster — the difference matters, so remember it.",
    },
    "Ra": {
        "rating": 4,
        "risks": [
            "Rahu periods tempt shortcuts that don't actually exist — the fast path here usually isn't.",
            "Restlessness can make you abandon something solid right before it would have paid off.",
        ],
        "opportunities": [
            "Unconventional, foreign, or non-traditional paths get real support this period.",
            "A good period to break from something outdated, if you've genuinely outgrown it and not just because you're bored.",
        ],
        "one_liner": "Rahu hands you intensity — whether it becomes progress or chaos is entirely up to you.",
    },
    "Ke": {
        "rating": 5,
        "risks": [
            "Motivation for ordinary goals may genuinely drop — don't ignore practical responsibilities because of it.",
            "Withdrawing too far from people who actually support you isn't insight, it's avoidance.",
        ],
        "opportunities": [
            "A legitimate period for letting go of something that's already been dead weight.",
            "Good period for reflection, spiritual practice, or quietly finishing unfinished business.",
        ],
        "one_liner": "Ketu doesn't build, it clears — useful only if you actually have something worth clearing.",
    },
}

_PERIOD_CONTENT_HI: dict[str, dict[str, Any]] = {
    "Su": {
        "rating": 6,
        "risks": [
            "अगर आप पहचान के लिए ज़्यादा ज़ोर लगाएंगे तो अधिकारियों या बॉस से टकराव हो सकता है।",
            "अति-आत्मविश्वास आपको ज़रूरी सलाह नज़रअंदाज़ करवा सकता है।",
        ],
        "opportunities": [
            "जो हक़ आपका बनता है — प्रमोशन, श्रेय, पहचान — उसे मांगने का मज़बूत समय है।",
            "इजाज़त का इंतज़ार करने के बजाय नेतृत्व संभालने का अच्छा समय है।",
        ],
        "one_liner": "यह दौर आपको सीधा खड़ा होने का इनाम देता है, चुप रहकर पहचान का इंतज़ार करने का नहीं।",
    },
    "Mo": {
        "rating": 6,
        "risks": [
            "कमज़ोर पल में लिया गया भावनात्मक फैसला छह महीने बाद अलग दिखेगा — इंतज़ार करें।",
            "पारिवारिक ज़िम्मेदारियां आपकी अपनी योजनाओं पर हावी हो सकती हैं अगर सीमा तय न करें।",
        ],
        "opportunities": [
            "अगर आप पहल करने को तैयार हैं तो बिगड़े पारिवारिक रिश्ते सुधारने का अच्छा समय है।",
            "घर और पारिवारिक फैसलों में अपनी अंतर्आत्मा पर भरोसा करें — फिलहाल यह असामान्य रूप से सटीक है।",
        ],
        "one_liner": "इस दौर में भावनाएं तेज़ हैं — जुड़ाव के लिए उपयोगी, बड़े फैसलों के लिए अविश्वसनीय।",
    },
    "Ma": {
        "rating": 5,
        "risks": [
            "अधीरता उस देरी से ज़्यादा महंगी पड़ेगी जिससे आप बचना चाहते हैं।",
            "अभी शुरू हुए विवाद सुलझने के बजाय बढ़ते हैं — लड़ाई सोच-समझकर चुनें।",
        ],
        "opportunities": [
            "जिस भी काम में तुरंत फैसले की ज़रूरत है, उसके लिए असली ऊर्जा है — यह इंतज़ार का समय नहीं।",
            "अगर सोच-समझकर किया जाए तो शारीरिक गतिविधि और प्रतिस्पर्धा अच्छा असर करेगी।",
        ],
        "one_liner": "यह दौर आपको ऊर्जा देता है, समझ नहीं — समझ खुद जोड़नी होगी।",
    },
    "Me": {
        "rating": 6,
        "risks": [
            "जल्दी में कहे गए शब्द आपकी सोच से ज़्यादा देर तक याद रखे जाते हैं — भेजने से पहले दोबारा पढ़ें।",
            "बहुत सी चीज़ों पर बिखरा ध्यान किसी भी काम को ठीक से पूरा नहीं करेगा।",
        ],
        "opportunities": [
            "अनुबंध, बातचीत और कागज़ी काम व्यवस्थित रहने पर अच्छे चलेंगे।",
            "सिर्फ़ मनोरंजन के लिए नहीं, बल्कि आगे काम आने वाली कोई चीज़ सीखने का मज़बूत समय है।",
        ],
        "one_liner": "यह दौर बातचीत पूरी करने का है, पांच नई शुरू करने का नहीं।",
    },
    "Ju": {
        "rating": 8,
        "risks": [
            "आशावाद ज़्यादा प्रतिबद्धता में बदल सकता है — हां कहने से पहले आंकड़े देख लें।",
            "अनुशासन के बिना विकास सिर्फ़ बाद में साफ़ करने के लिए एक बड़ी गड़बड़ है।",
        ],
        "opportunities": [
            "विवाह, शिक्षा या आर्थिक विकास के लिए यह सबसे अनुकूल दौरों में से एक है।",
            "जिस सोचे-समझे जोखिम को टाल रहे थे, उसके लिए अच्छा समर्थन है।",
        ],
        "one_liner": "इस दौर में दरवाज़ा खुला है — असली जोखिम सिर्फ़ लापरवाही से अंदर जाने में है।",
    },
    "Ve": {
        "rating": 7,
        "risks": [
            "सुविधा आलस्य में बदल सकती है — यह दौर खुद आपको आगे नहीं धकेलेगा, खुद धक्का देना होगा।",
            "सुविधा या दिखावे पर ज़्यादा खर्च ही इस दौर का सबसे बड़ा नुकसान होगा।",
        ],
        "opportunities": [
            "रिश्तों, रचनात्मक काम और अनदेखी की गई चीज़ें सुधारने के लिए वाकई अच्छा समय है।",
            "सिर्फ़ झेलने के बजाय अपने माहौल और रिश्तों में निवेश करने का अच्छा समय है।",
        ],
        "one_liner": "यह दौर स्वाभाविक रूप से सुखद है — सुखद को उत्पादक मत समझ लें।",
    },
    "Sa": {
        "rating": 5,
        "risks": [
            "प्रगति आपकी चाहत से धीमी होगी, और इसे नज़रअंदाज़ करना सिर्फ़ निराशा बढ़ाएगा।",
            "शनि के दौर में अकेलापन बढ़ता है — इसे पूरी तरह अलग हो जाने का इशारा मत समझें।",
        ],
        "opportunities": [
            "अभी सावधानी से बनाई गई चीज़ें वाकई टिकती हैं — शनि मेहनत को नहीं, शॉर्टकट को सज़ा देता है।",
            "जिस चीज़ से बच रहे थे, उसमें अनुशासन लाने का सही समय है।",
        ],
        "one_liner": "यह दौर मुश्किल है, तबाही नहीं — यह फ़र्क़ मायने रखता है, इसे याद रखें।",
    },
    "Ra": {
        "rating": 4,
        "risks": [
            "राहु के दौर शॉर्टकट का लालच देते हैं जो असल में मौजूद नहीं होते — तेज़ रास्ता अक्सर तेज़ नहीं होता।",
            "बेचैनी आपसे कोई मज़बूत चीज़ ठीक उसके फल देने से पहले छुड़वा सकती है।",
        ],
        "opportunities": [
            "अपरंपरागत, विदेशी या नए रास्तों को इस दौर में असली समर्थन मिलता है।",
            "अगर वाकई आगे बढ़ चुके हैं, सिर्फ़ बोरियत से नहीं, तो पुरानी चीज़ छोड़ने का अच्छा समय है।",
        ],
        "one_liner": "राहु आपको तीव्रता देता है — यह प्रगति बनेगी या अफ़रा-तफ़री, यह पूरी तरह आप पर निर्भर है।",
    },
    "Ke": {
        "rating": 5,
        "risks": [
            "सामान्य लक्ष्यों के लिए प्रेरणा वाकई कम हो सकती है — इस वजह से व्यावहारिक ज़िम्मेदारियां नज़रअंदाज़ न करें।",
            "जो लोग वाकई साथ देते हैं उनसे बहुत दूर हट जाना समझ नहीं, बचना है।",
        ],
        "opportunities": [
            "जो चीज़ पहले से बेकार बोझ बन चुकी है, उसे छोड़ने का सही समय है।",
            "आत्मचिंतन, आध्यात्मिक अभ्यास या चुपचाप अधूरा काम पूरा करने के लिए अच्छा समय है।",
        ],
        "one_liner": "केतु बनाता नहीं, साफ़ करता है — तभी उपयोगी है जब साफ़ करने लायक कुछ हो।",
    },
}

# Per-mahadasha-lord whole-life framing for complete_kundali's brutal_truth /
# core_strength / core_challenge — same hand-written-variety principle.
_LIFE_FRAMING_EN: dict[str, dict[str, str]] = {
    "Su": {"brutal_truth": "You want recognition more than you admit — stop waiting to be noticed and start being visible.",
           "core_strength": "Natural authority and clarity of purpose.", "core_challenge": "Difficulty accepting feedback that bruises the ego."},
    "Mo": {"brutal_truth": "Your moods run the show more than your plans do — that's not weakness, but it is worth admitting.",
           "core_strength": "Emotional attunement and adaptability.", "core_challenge": "Letting feelings, not facts, make the final call."},
    "Ma": {"brutal_truth": "You have more drive than patience, and it shows in what you leave unfinished.",
           "core_strength": "Decisiveness and raw initiative.", "core_challenge": "Impulsiveness that outruns judgment."},
    "Me": {"brutal_truth": "You think faster than you commit — that's useful for ideas and costly for follow-through.",
           "core_strength": "Sharp, adaptable thinking.", "core_challenge": "Scattering focus across too many threads."},
    "Ju": {"brutal_truth": "You've been handed real advantages — the only way you waste this chart is by not using them.",
           "core_strength": "Genuine optimism backed by good judgment.", "core_challenge": "Overextending because things have gone well so far."},
    "Ve": {"brutal_truth": "You're built for comfort, not for struggle — which means you have to manufacture your own discipline.",
           "core_strength": "Warmth and an eye for what makes life good.", "core_challenge": "Complacency once things feel comfortable enough."},
    "Sa": {"brutal_truth": "Nothing about your life has come easily, and pretending otherwise would be the actual lie.",
           "core_strength": "Discipline and the ability to outlast almost anyone.", "core_challenge": "A tendency to isolate rather than ask for help."},
    "Ra": {"brutal_truth": "You're drawn to the unconventional path — whether that becomes your edge or your undoing depends entirely on discipline you don't naturally have.",
           "core_strength": "Willingness to break from convention.", "core_challenge": "Restlessness that abandons things too early."},
    "Ke": {"brutal_truth": "Part of you has already checked out of the ordinary race — the question is whether you're using that clarity or just drifting.",
           "core_strength": "Genuine capacity for detachment and insight.", "core_challenge": "Disengaging from responsibilities that still need you."},
}
_LIFE_FRAMING_HI: dict[str, dict[str, str]] = {
    "Su": {"brutal_truth": "आप जितना मानते हैं उससे ज़्यादा पहचान चाहते हैं — पहचाने जाने का इंतज़ार बंद करें, दिखना शुरू करें।",
           "core_strength": "स्वाभाविक नेतृत्व क्षमता और स्पष्ट उद्देश्य।", "core_challenge": "अहम को चोट पहुंचाने वाली सलाह स्वीकार करने में कठिनाई।"},
    "Mo": {"brutal_truth": "आपकी योजनाओं से ज़्यादा आपका मूड फैसले करता है — यह कमज़ोरी नहीं, पर मानने लायक बात है।",
           "core_strength": "भावनात्मक समझ और लचीलापन।", "core_challenge": "तथ्यों की बजाय भावनाओं को अंतिम फैसला लेने देना।"},
    "Ma": {"brutal_truth": "आपमें धैर्य से ज़्यादा जोश है, और यह उन अधूरे कामों में दिखता है जो आप छोड़ देते हैं।",
           "core_strength": "निर्णायक क्षमता और पहल करने का जज़्बा।", "core_challenge": "आवेग जो समझ से आगे निकल जाता है।"},
    "Me": {"brutal_truth": "आप प्रतिबद्ध होने से ज़्यादा तेज़ सोचते हैं — यह विचारों के लिए उपयोगी है, पूरा करने के लिए महंगा।",
           "core_strength": "तेज़ और लचीली सोच।", "core_challenge": "ध्यान को बहुत सी चीज़ों में बिखेर देना।"},
    "Ju": {"brutal_truth": "आपको असली फ़ायदे मिले हैं — इस कुंडली को बर्बाद करने का बस एक तरीका है: इनका इस्तेमाल न करना।",
           "core_strength": "अच्छे निर्णय के साथ सच्चा आशावाद।", "core_challenge": "अब तक सब ठीक चलने की वजह से ज़्यादा फैला लेना।"},
    "Ve": {"brutal_truth": "आप सुविधा के लिए बने हैं, संघर्ष के लिए नहीं — इसलिए अपना अनुशासन खुद बनाना होगा।",
           "core_strength": "गर्मजोशी और अच्छी चीज़ों को पहचानने की नज़र।", "core_challenge": "चीज़ें आरामदायक लगते ही आलस्य आ जाना।"},
    "Sa": {"brutal_truth": "आपके जीवन में कुछ भी आसानी से नहीं मिला, और इसके उलट मानना ही असली झूठ होगा।",
           "core_strength": "अनुशासन और लगभग हर किसी से ज़्यादा टिके रहने की क्षमता।", "core_challenge": "मदद मांगने के बजाय खुद को अलग कर लेने की प्रवृत्ति।"},
    "Ra": {"brutal_truth": "आप अपरंपरागत रास्ते की ओर खिंचते हैं — यह आपकी ताकत बनेगा या नुकसान, यह उस अनुशासन पर निर्भर है जो आपमें स्वाभाविक रूप से नहीं है।",
           "core_strength": "परंपरा से हटकर सोचने की इच्छाशक्ति।", "core_challenge": "बेचैनी जो चीज़ों को समय से पहले छोड़ देती है।"},
    "Ke": {"brutal_truth": "आपका एक हिस्सा सामान्य दौड़ से पहले ही बाहर निकल चुका है — सवाल यह है कि क्या आप उस स्पष्टता का उपयोग कर रहे हैं या बस बह रहे हैं।",
           "core_strength": "अलगाव और अंतर्दृष्टि की सच्ची क्षमता।", "core_challenge": "अब भी ज़रूरी ज़िम्मेदारियों से खुद को अलग कर लेना।"},
}


# Free-text chat routing (no LLM): map a handful of real-life topics to the
# house that classically governs them, and to the keywords (English, Hindi,
# and common Hinglish spellings) a user might ask about that topic in. This
# lets chat_reply answer from the SAME real per-house facts already computed
# in chart_explanation_service, rather than a canned "please clarify" stub.
_TOPIC_HOUSE: dict[str, int] = {
    "career": 10, "money": 2, "marriage": 7, "health": 6, "family": 4,
    "education": 9, "friends": 11, "travel": 9, "children": 5, "siblings": 3,
}
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "career": [
        "career", "job", "profession", "promotion", "business", "naukri", "karobar",
        "नौकरी", "करियर", "पेशा", "व्यापार", "प्रमोशन",
    ],
    "money": [
        "money", "finance", "financial", "wealth", "income", "paisa", "dhan",
        "पैसा", "धन", "आर्थिक", "वित्त",
    ],
    "marriage": [
        "marriage", "marry", "married", "shaadi", "vivah", "husband", "wife", "spouse", "partner",
        "शादी", "विवाह", "पति", "पत्नी", "जीवनसाथी",
    ],
    "health": ["health", "sick", "illness", "disease", "tabiyat", "सेहत", "स्वास्थ्य", "बीमारी", "तबीयत"],
    "family": ["family", "parents", "mother", "father", "ghar", "परिवार", "माता", "पिता", "घर"],
    "education": ["study", "studies", "education", "exam", "padhai", "पढ़ाई", "शिक्षा", "परीक्षा"],
    "friends": ["friend", "friends", "dost", "दोस्त", "मित्र"],
    "travel": ["travel", "trip", "abroad", "videsh", "safar", "यात्रा", "विदेश", "सफर"],
    "children": ["child", "children", "baby", "santan", "औलाद", "संतान", "बच्च"],
    "siblings": ["sibling", "brother", "sister", "bhai", "behen", "भाई", "बहन"],
}
_DOSHA_KEYS = {"manglik", "kaal_sarp", "kemadruma"}
_DOSHA_KEYWORDS = [
    "dosha", "dosh", "manglik", "mangal dosh", "kaal sarp", "kaalsarp", "kemadruma",
    "दोष", "मंगलिक", "कालसर्प", "काल सर्प", "केमद्रुम",
]
_YOGA_KEYWORDS = ["yoga", "raj yoga", "gajakesari", "mahapurusha", "योग"]
_DASHA_KEYWORDS = [
    "dasha", "mahadasha", "antardasha", "period", "when will", "kab", "कब",
    "दशा", "महादशा", "अंतर्दशा",
]
_TODAY_KEYWORDS = ["today", "aaj", "आज", "daily", "din"]

# "When will I get married" needs the actual Prediction Engine (real dasha/
# transit windows), not the static 7th-house natal-placement fact the plain
# "marriage" topic answers with — so it's detected as its own category,
# reusing the marriage keyword list ANDed with a timing hint, checked before
# the generic "dasha" category (which would otherwise swallow "when will…").
_TIMING_HINT_KEYWORDS = [
    "when", "kab", "कब", "which year", "what age", "kis umar", "किस उम्र",
    # Colloquial future-outcome phrasing ("will I ever settle abroad?", "will
    # I get married?") is just as much a timing question as an explicit
    # "when" — real users ask it this way at least as often.
    "will i", "will my", "क्या मैं", "क्या मेरी", "क्या मेरा",
]
# "How's my year going" / "how's 2026 looking" likewise needs the real
# Varshaphala-based Year-Ahead engine, not a bare dasha-lord sentence.
# Deliberately NOT bare "this year"/"next year"/"yearly" — those show up as
# ordinary time qualifiers on plain topic questions too (e.g. "how's my
# career looking this year?" is a career question, not a whole-year-outlook
# one), so they'd wrongly hijack every topic question that mentions a
# timeframe. A standalone 4-digit year (e.g. "2026") is a much stronger,
# low-collision signal and is checked separately via _YEAR_TOKEN_RE.
_YEAR_AHEAD_PHRASES = [
    "how is my year", "how's my year", "hows my year", "my year going", "year ahead", "yearly outlook",
    "how does my year look", "how will my year",
    "saal kaisa", "yeh saal kaisa", "agla saal kaisa", "saal kaisa jayega", "saal kaisa rahega",
    "साल कैसा", "यह साल कैसा", "अगला साल कैसा", "वर्ष कैसा",
]
_YEAR_TOKEN_RE = re.compile(r"\b20[2-4]\d\b")  # a bare "2026"-style year, 2020-2049


def message_mentions_marriage_timing(message: str) -> bool:
    """True for a real WHEN-will-I-get-married question — the caller (see
    app.api.v1.chat) uses this to decide whether to fetch the marriage-timing
    engine's output at all, avoiding that computation on unrelated chat
    messages."""
    lowered = message.lower()
    has_marriage = any(k in lowered for k in _TOPIC_KEYWORDS["marriage"])
    has_timing = any(k in lowered for k in _TIMING_HINT_KEYWORDS)
    return has_marriage and has_timing


def message_mentions_year_ahead(message: str) -> bool:
    """True for a real how's-my-year-going question — used the same way as
    message_mentions_marriage_timing above."""
    lowered = message.lower()
    if _YEAR_TOKEN_RE.search(lowered):
        return True
    return any(k in lowered for k in _YEAR_AHEAD_PHRASES)


# Same pattern as marriage timing, generalized to career/wealth/children —
# reuse the existing topic keyword lists, ANDed with the same timing hint,
# so a plain non-timing topic question ("what career suits me?") still gets
# the existing static house-text answer, unchanged.
def message_mentions_career_timing(message: str) -> bool:
    lowered = message.lower()
    has_career = any(k in lowered for k in _TOPIC_KEYWORDS["career"])
    has_timing = any(k in lowered for k in _TIMING_HINT_KEYWORDS)
    return has_career and has_timing


def message_mentions_wealth_timing(message: str) -> bool:
    lowered = message.lower()
    has_money = any(k in lowered for k in _TOPIC_KEYWORDS["money"])
    has_timing = any(k in lowered for k in _TIMING_HINT_KEYWORDS)
    return has_money and has_timing


def message_mentions_children_timing(message: str) -> bool:
    lowered = message.lower()
    has_children = any(k in lowered for k in _TOPIC_KEYWORDS["children"])
    has_timing = any(k in lowered for k in _TIMING_HINT_KEYWORDS)
    return has_children and has_timing


# Deliberately its own keyword list, not the generic "travel" topic (trip/
# safar/etc., which stays a plain 9th-house answer) — a genuine foreign-
# relocation question needs the life-event engine, an ordinary domestic-trip
# question doesn't.
_FOREIGN_TRAVEL_KEYWORDS = [
    "abroad", "foreign country", "foreign", "immigrate", "immigration", "settle abroad",
    "move overseas", "relocate abroad", "videsh", "pravas", "विदेश", "प्रवास",
]


def message_mentions_foreign_travel_timing(message: str) -> bool:
    lowered = message.lower()
    has_foreign = any(k in lowered for k in _FOREIGN_TRAVEL_KEYWORDS)
    has_timing = any(k in lowered for k in _TIMING_HINT_KEYWORDS)
    return has_foreign and has_timing


# Shared chat-answer composer for the 4 life-event-timing categories — same
# "top window + reason, or an honest no-window-found line" shape as the
# marriage_timing branch below, factored out once instead of repeated 4x
# since (unlike marriage) these have no bespoke copy of their own.
_LIFE_EVENT_LABEL_EN: dict[str, str] = {
    "career_timing": "a career or job change",
    "wealth_timing": "your financial growth",
    "children_timing": "having a child",
    "foreign_travel_timing": "foreign travel or relocation",
}
_LIFE_EVENT_LABEL_HI: dict[str, str] = {
    "career_timing": "करियर या नौकरी में बदलाव",
    "wealth_timing": "आपकी आर्थिक वृद्धि",
    "children_timing": "संतान प्राप्ति",
    "foreign_travel_timing": "विदेश यात्रा या स्थानांतरण",
}
_LIFE_EVENT_CONTEXT_KEY: dict[str, str] = {
    "career_timing": "career_timing_windows",
    "wealth_timing": "wealth_timing_windows",
    "children_timing": "children_timing_windows",
    "foreign_travel_timing": "foreign_travel_timing_windows",
}


def _life_event_chat_answer(category: str, context: dict[str, Any], hi: bool) -> str:
    windows: list[dict[str, Any]] = context.get(_LIFE_EVENT_CONTEXT_KEY[category]) or []
    label = (_LIFE_EVENT_LABEL_HI if hi else _LIFE_EVENT_LABEL_EN)[category]
    if windows:
        top = windows[0]
        if hi:
            return (
                f"आपकी कुंडली के अनुसार, {label} के लिए सबसे संभावित समय "
                f"{top['start_date']} से {top['end_date']} के बीच लगता है। {top['reason']} ध्यान रहे, यह एक "
                "संभावित अनुकूल समय है, कोई निश्चित तारीख नहीं।"
            )
        return (
            f"Based on your chart, the most likely window for {label} looks like "
            f"{top['start_date']} to {top['end_date']}. {top['reason']} Keep in mind this is a probable "
            "favorable window, not a guaranteed exact date."
        )
    return (
        "मुझे अभी जितनी अवधि खोजी है उसमें कोई खास तौर पर अनुकूल समय नहीं मिला।"
        if hi
        else "I didn't find a strongly favorable window in the period I can currently search."
    )

# Which Rishi persona owns which question category — the specialization the
# user asked for ("Vasishtha only answers life direction, Parashara only
# timing, Gargi only relationships") rather than all five personas answering
# every topic identically. Categories are the 4 special ones (today/dasha/
# dosha/yoga) plus every key in _TOPIC_HOUSE; every category is owned by
# exactly one Rishi so a reverse lookup (_CATEGORY_RISHI) is unambiguous.
_RISHI_SPECIALTY: dict[str, set[str]] = {
    "vasishtha": {"education", "travel", "foreign_travel_timing"},
    "parashara": {"dasha", "today", "year_ahead"},
    "gargi": {"marriage", "family", "friends", "siblings", "children", "marriage_timing", "children_timing"},
    "agastya": {"dosha", "yoga", "health"},
    "bhrigu": {"career", "money", "career_timing", "wealth_timing"},
}
_CATEGORY_RISHI: dict[str, str] = {
    category: rishi for rishi, categories in _RISHI_SPECIALTY.items() for category in categories
}
_RISHI_NAME_EN = {"vasishtha": "Vasishtha", "parashara": "Parashara", "gargi": "Gargi", "agastya": "Agastya", "bhrigu": "Bhrigu"}
_RISHI_NAME_HI = {"vasishtha": "वशिष्ठ", "parashara": "पराशर", "gargi": "गार्गी", "agastya": "अगस्त्य", "bhrigu": "भृगु"}
_RISHI_DOMAIN_EN = {
    "vasishtha": "life direction and purpose",
    "parashara": "timing — your dasha and transits",
    "gargi": "relationships and family",
    "agastya": "doshas, yogas, and inner balance",
    "bhrigu": "career and money",
}
_RISHI_DOMAIN_HI = {
    "vasishtha": "जीवन की दिशा और उद्देश्य",
    "parashara": "समय — आपकी दशा और गोचर",
    "gargi": "रिश्तों और परिवार",
    "agastya": "दोष, योग और आंतरिक संतुलन",
    "bhrigu": "करियर और धन",
}
# Each Rishi's own personality-flavoured lead-in, spoken before a real
# chart-grounded answer (house_breakdown/dasha/dosha/yoga/today text) — a
# rotating choice (see _pick_variant) so asking the same Rishi more than once
# in a conversation doesn't read as the same canned line every time. This is
# the "sounds like a real person, not a repeated template" fix: the
# underlying FACT stays exactly the same (never invented), only how it's
# introduced varies.
_RISHI_LEAD_IN_EN: dict[str, list[str]] = {
    "vasishtha": [
        "Looking at your chart, here's what stands out:",
        "This is what your placements tell me:",
        "Let me walk you through what I see:",
    ],
    "parashara": [
        "Based on the calculations in your chart:",
        "Cross-referencing your placements and timing:",
        "Here's what the numbers show:",
    ],
    "gargi": [
        "Let's see what your chart says about this:",
        "Here's what I notice, looking closely:",
        "This is what comes up when I look at this part of your chart:",
    ],
    "agastya": [
        "Sit with this for a moment — here's what I see:",
        "Here's what your chart is pointing toward:",
        "Let's look at this together:",
    ],
    "bhrigu": [
        "Here's the direct read, no sugarcoating:",
        "Straight from your chart:",
        "Let's get into it:",
    ],
}
_RISHI_LEAD_IN_HI: dict[str, list[str]] = {
    "vasishtha": [
        "आपकी कुंडली देखने पर यह सामने आता है:",
        "आपकी स्थिति यही बताती है:",
        "मैं आपको बताता हूं मुझे क्या दिख रहा है:",
    ],
    "parashara": [
        "आपकी कुंडली की गणना के अनुसार:",
        "आपकी स्थिति और समय को मिलाकर देखें तो:",
        "आंकड़े यह दिखाते हैं:",
    ],
    "gargi": [
        "देखते हैं आपकी कुंडली इस बारे में क्या कहती है:",
        "ध्यान से देखने पर यह दिखता है:",
        "आपकी कुंडली के इस हिस्से में यह सामने आता है:",
    ],
    "agastya": [
        "एक पल रुककर देखें — मुझे यह दिख रहा है:",
        "आपकी कुंडली इस ओर इशारा कर रही है:",
        "आइए इसे साथ में देखते हैं:",
    ],
    "bhrigu": [
        "सीधी बात, बिना लाग-लपेट के:",
        "सीधे आपकी कुंडली से:",
        "चलिए सीधे मुद्दे पर आते हैं:",
    ],
}

_RISHI_FALLBACK_EN: dict[str, list[str]] = {
    "vasishtha": [
        "I speak to your life direction and purpose — ask me things like \"what's my life purpose\" or "
        "\"what should I focus on in life\".",
        "Life direction is where I can actually help — try asking about your purpose, your path, or what "
        "you should be focusing on right now.",
        "That's a bit outside what I read for you. I'm here for life direction and purpose — ask me about "
        "your path or what you're meant to focus on.",
    ],
    "parashara": [
        "I read timing — your dasha and transits. Ask me things like \"what dasha am I running\" or "
        "\"what does today look like\".",
        "Timing is my domain — your current dasha, today's transits, that sort of thing. Ask me about those.",
        "I'd rather stay useful than guess — ask me about your dasha, your transits, or what today looks like.",
    ],
    "gargi": [
        "I focus on relationships and family. Ask me things like \"how's my marriage looking\" or "
        "\"what about my family life\".",
        "Relationships and family are where I can really help — try asking about your marriage, or your "
        "family life.",
        "That's not quite my area, but I'd love to talk about your relationships or family — ask me about those.",
    ],
    "agastya": [
        "I look at doshas, yogas, and inner balance. Ask me things like \"am I manglik\" or "
        "\"do I have any yoga in my chart\".",
        "Doshas, yogas, and inner balance are what I read — ask me if you're manglik, or what yogas your "
        "chart carries.",
        "I'm here for the deeper patterns — doshas, yogas, inner balance. Ask me about those.",
    ],
    "bhrigu": [
        "I focus on career and money. Ask me things like \"how's my career looking\" or "
        "\"what about my finances\".",
        "Career and money are what I actually read for you — ask me how your career's looking, or about your finances.",
        "That's outside my read, but ask me about your career or money and I'll go deep.",
    ],
}
_RISHI_FALLBACK_HI: dict[str, list[str]] = {
    "vasishtha": [
        "मैं आपकी जीवन दिशा और उद्देश्य पर बात करता हूं — मुझसे पूछें जैसे \"मेरे जीवन का उद्देश्य क्या है\" या "
        "\"मुझे किस पर ध्यान देना चाहिए\"।",
        "जीवन दिशा वही है जहां मैं वाकई मदद कर सकता हूं — अपने उद्देश्य, अपने रास्ते के बारे में पूछें।",
        "यह मेरे विषय से थोड़ा बाहर है। मैं जीवन दिशा और उद्देश्य के लिए हूं — अपने रास्ते के बारे में पूछें।",
    ],
    "parashara": [
        "मैं समय देखता हूं — आपकी दशा और गोचर। मुझसे पूछें जैसे \"मेरी अभी कौन सी दशा चल रही है\" या "
        "\"आज का दिन कैसा है\"।",
        "समय मेरा विषय है — आपकी मौजूदा दशा, आज के गोचर। इनके बारे में पूछें।",
        "अंदाज़ा लगाने से बेहतर है काम की बात — अपनी दशा या आज के दिन के बारे में पूछें।",
    ],
    "gargi": [
        "मैं रिश्तों और परिवार पर ध्यान देती हूं। मुझसे पूछें जैसे \"मेरी शादी कैसी रहेगी\" या "
        "\"मेरे परिवार के बारे में क्या\"।",
        "रिश्ते और परिवार वही हैं जहां मैं वाकई मदद कर सकती हूं — अपनी शादी या परिवार के बारे में पूछें।",
        "यह मेरा विषय नहीं, पर मुझे आपके रिश्तों या परिवार पर बात करना अच्छा लगेगा — इनके बारे में पूछें।",
    ],
    "agastya": [
        "मैं दोष, योग और आंतरिक संतुलन देखता हूं। मुझसे पूछें जैसे \"क्या मैं मंगलिक हूं\" या "
        "\"मेरी कुंडली में कोई योग है क्या\"।",
        "दोष, योग और आंतरिक संतुलन वही है जो मैं पढ़ता हूं — पूछें कि आप मंगलिक हैं या नहीं, या कोई योग है क्या।",
        "मैं गहरे पैटर्न के लिए हूं — दोष, योग, आंतरिक संतुलन। इनके बारे में पूछें।",
    ],
    "bhrigu": [
        "मैं करियर और धन पर ध्यान देता हूं। मुझसे पूछें जैसे \"मेरा करियर कैसा रहेगा\" या "
        "\"मेरी आर्थिक स्थिति के बारे में क्या\"।",
        "करियर और धन ही असल में मेरा विषय है — अपने करियर या आर्थिक स्थिति के बारे में पूछें।",
        "यह मेरे विषय से बाहर है, पर करियर या पैसों के बारे में पूछें, मैं गहराई से बताऊंगा।",
    ],
}

_RISHI_POINTER_EN = [
    "For more detail on this, chat with {owner} — it's their specialty.",
    "{owner} goes much deeper on this — worth asking them too.",
    "If you want the full picture here, {owner} is who to ask.",
]
_RISHI_POINTER_HI = [
    "इस पर और जानने के लिए {owner} से बात करें — यह उनकी विशेषज्ञता का विषय है।",
    "{owner} इस पर कहीं ज़्यादा गहराई से बता सकते हैं — उनसे भी पूछें।",
    "इसकी पूरी तस्वीर के लिए {owner} से पूछना सही रहेगा।",
]


def _pick_variant(variants: list[str], history: list[dict[str, str]]) -> str:
    """Deterministic (no LLM/randomness) rotation through a set of hand-
    written phrasings, keyed off how many messages exist in this
    conversation so far — so asking the same Rishi twice in one chat gets a
    different phrasing each time, without ever inventing new content."""
    return variants[len(history) % len(variants)]


def _rishi_pointer(hi: bool, category: str, history: list[dict[str, str]]) -> str:
    """A short suffix pointing to the Rishi who actually specializes in
    `category`, appended AFTER a real answer — not a refusal on its own. A
    user asking Vasishtha about their marriage still gets a real answer from
    the chart; they're just also told Gargi goes deeper on it."""
    owner_id = _CATEGORY_RISHI[category]
    owner_name = _RISHI_NAME_HI[owner_id] if hi else _RISHI_NAME_EN[owner_id]
    template = _pick_variant(_RISHI_POINTER_HI if hi else _RISHI_POINTER_EN, history)
    return template.format(owner=owner_name)


def _rishi_refusal(hi: bool, asking_rishi_id: str, category: str) -> str:
    """Used only when no real answer exists to give at all (e.g. a category
    the chart has no data for) — states the asking Rishi's own domain and
    points to the one who actually owns this topic."""
    owner_id = _CATEGORY_RISHI[category]
    owner_name = _RISHI_NAME_HI[owner_id] if hi else _RISHI_NAME_EN[owner_id]
    own_domain = _RISHI_DOMAIN_HI[asking_rishi_id] if hi else _RISHI_DOMAIN_EN[asking_rishi_id]
    if hi:
        return (
            f"यह सवाल {owner_name} के विषय क्षेत्र में आता है, मेरे नहीं — मैं {own_domain} पर बात करता/करती हूं। "
            f"कृपया यह सवाल {owner_name} से पूछें, वे इसमें गहराई से बता सकेंगे।"
        )
    return (
        f"That's really {owner_name}'s domain, not mine — I focus on {own_domain}. Go ask {owner_name} about "
        "that, they'll go deep on it."
    )


class TemplateInterpreter(Interpreter):
    async def daily_horoscope(self, context: dict[str, Any], language: Language, mode: Mode) -> dict[str, Any]:
        lord = context.get("antardasha_lord_key", "Mo")
        tone = (_TONE_BY_LORD_HI if language == "hi" else _TONE_BY_LORD_EN).get(lord, "steady")

        highlights = context.get("transit_highlights", [])
        houses = [h["house_from_moon"] for h in highlights[:2]] or [1, 10]
        focus_map = _FOCUS_BY_HOUSE_HI if language == "hi" else _FOCUS_BY_HOUSE_EN
        focus_areas = [focus_map.get(h, focus_map[1]) for h in houses]

        if language == "hi":
            tip = "आज बड़े फैसले जल्दबाज़ी में न लें।"
            summary_text = f"आज का दिन {tone} रहेगा। ध्यान {' और '.join(focus_areas)} पर रहेगा। {tip}"
        else:
            tip = "Avoid rushing into big decisions today."
            summary_text = f"Today feels {tone}. Focus lands on {' and '.join(focus_areas)}. {tip}"

        return {"tone": tone, "focus_areas": focus_areas, "tip": tip, "summary_text": summary_text}

    async def period_analysis(self, context: dict[str, Any], language: Language, mode: Mode) -> dict[str, Any]:
        maha_key = context.get("mahadasha_lord_key", "Mo")
        antar_key = context.get("antardasha_lord_key", maha_key)
        maha_name = context.get("mahadasha_lord", "")
        antar_name = context.get("antardasha_lord", "")

        content_pool = _PERIOD_CONTENT_HI if language == "hi" else _PERIOD_CONTENT_EN
        maha_content = content_pool.get(maha_key, content_pool["Mo"])
        antar_content = content_pool.get(antar_key, content_pool["Mo"])

        # Antardasha (the immediate lord) dominates the day-to-day experience;
        # mahadasha only sets the broader backdrop — weight the rating 2:1
        # toward the antardasha lord accordingly.
        rating = round((maha_content["rating"] + 2 * antar_content["rating"]) / 3)

        if language == "hi":
            theme = f"{maha_name} महादशा की पृष्ठभूमि में {antar_name} अंतर्दशा — इसी का असर फिलहाल हावी है।"
        else:
            theme = f"{antar_name} sub-period, running inside {maha_name}'s broader Mahadasha — {antar_name} is what's actually driving this stretch."

        return {
            "rating": rating,
            "theme": theme,
            "risks": antar_content["risks"],
            "opportunities": antar_content["opportunities"],
            "summary": antar_content["one_liner"],
        }

    async def chart_explanation(
        self, context: dict[str, Any], chart_type: Literal["D1", "D9", "D10"], language: Language, mode: Mode
    ) -> str:
        lagna = context.get("lagna_sign", "")
        if language == "hi":
            return f"आपकी {chart_type} कुंडली में लग्न {lagna} है। यह आपके स्वभाव और जीवन के दृष्टिकोण की नींव दिखाता है।"
        return f"In your {chart_type} chart, the Lagna is {lagna}. This is the foundation of your temperament and outlook on life."

    async def chart_summary(
        self, context: dict[str, Any], chart_type: Literal["D1", "D9", "D10"], language: Language, mode: Mode
    ) -> dict[str, Any]:
        lagna = context.get("lagna_sign", "")
        planets = context.get("planets", [])
        retrograde_names = [p["planet"] for p in planets if p.get("retrograde")]

        if language == "hi":
            summary = f"{chart_type} कुंडली में लग्न {lagna} है, जो आपके दृष्टिकोण की नींव है।"
            key_points = [f"लग्न: {lagna}"]
            if retrograde_names:
                key_points.append(f"वक्री ग्रह: {', '.join(retrograde_names)}")
            key_points.append("हर ग्रह की भाव स्थिति नीचे कुंडली में देखें।")
        else:
            summary = f"In this {chart_type} chart, the Lagna is {lagna} — the foundation of your outlook here."
            key_points = [f"Lagna: {lagna}"]
            if retrograde_names:
                key_points.append(f"Retrograde: {', '.join(retrograde_names)}")
            key_points.append("See the chart below for each planet's exact house placement.")

        return {"summary": summary, "key_points": key_points}

    async def manglik_explanation(self, context: dict[str, Any], language: Language, mode: Mode) -> dict[str, Any]:
        is_manglik = context.get("is_manglik", False)
        house_lagna = context.get("mars_house_from_lagna")
        house_moon = context.get("mars_house_from_moon")
        own_sign = context.get("mars_in_own_sign", False)

        if language == "hi":
            summary = "आप मंगलिक हैं." if is_manglik else "आप मंगलिक नहीं हैं."
            details = [
                f"लग्न से मंगल {_hindi_house(house_lagna)} में है।",
                f"चंद्रमा से मंगल {_hindi_house(house_moon)} में है।",
            ]
            cancellations = (
                ["मंगल अपनी ही राशि में है, जिसे परंपरागत रूप से राहत देने वाला कारक माना जाता है।"]
                if own_sign
                else []
            )
            relationship_note = (
                "कई परिवार साथी की कुंडली से सावधानी से मिलान करना पसंद करते हैं। किसी अनुभवी ज्योतिषी से सलाह लेना सहायक हो सकता है।"
                if is_manglik
                else "इस स्थिति के आधार पर विवाह में कोई विशेष रुकावट नहीं दिखती।"
            )
        else:
            summary = "You are Manglik." if is_manglik else "You are not Manglik."
            details = [
                f"Mars sits in the {house_lagna}th house counted from your Lagna.",
                f"Mars sits in the {house_moon}th house counted from your Moon.",
            ]
            cancellations = (
                ["Mars is in its own sign, traditionally considered a mitigating factor."] if own_sign else []
            )
            relationship_note = (
                "Many families choose to match this carefully with a partner's chart. A qualified astrologer "
                "can help if you'd like a second opinion."
                if is_manglik
                else "Nothing about this placement suggests a barrier to marriage."
            )

        return {
            "summary": summary, "details": details, "cancellations": cancellations,
            "relationship_note": relationship_note,
        }

    async def complete_kundali(self, context: dict[str, Any], language: Language, mode: Mode) -> dict[str, Any]:
        lagna = context.get("lagna_sign", "")
        maha_key = context.get("mahadasha_lord_key", "Mo")
        maha_name = context.get("mahadasha_lord", "")
        maha_house = context.get("mahadasha_lord_house")
        maha_dignity = context.get("mahadasha_lord_dignity", "neutral")

        lagna_lord_key: PlanetKey = context.get("lagna_lord_key", "Mo")
        lagna_lord_house = context.get("lagna_lord_house", 1)
        lagna_lord_dignity = context.get("lagna_lord_dignity", "neutral")

        tenth_lord_key: PlanetKey = context.get("tenth_lord_key", "Mo")
        tenth_lord_house = context.get("tenth_lord_house", 10)
        tenth_lord_dignity = context.get("tenth_lord_dignity", "neutral")

        seventh_lord_key: PlanetKey = context.get("seventh_lord_key", "Mo")
        seventh_lord_house = context.get("seventh_lord_house", 7)
        seventh_lord_dignity = context.get("seventh_lord_dignity", "neutral")

        sixth_lord_key: PlanetKey = context.get("sixth_lord_key", "Mo")
        sixth_lord_house = context.get("sixth_lord_house", 6)
        sixth_lord_dignity = context.get("sixth_lord_dignity", "neutral")

        strongest_planet_key: PlanetKey | None = context.get("strongest_planet_key")
        weakest_planet_key: PlanetKey | None = context.get("weakest_planet_key")

        framing_pool = _LIFE_FRAMING_HI if language == "hi" else _LIFE_FRAMING_EN
        # brutal_truth is about the CURRENT chapter of life, so it stays keyed
        # to the running Mahadasha lord. core_strength/core_challenge are
        # chart-structural (they shouldn't change just because a new dasha
        # started), so each is independently keyed to the real dignity-based
        # fact for THIS chart — the first exalted/own-sign planet for
        # strength, the first debilitated planet for challenge — falling back
        # to the Mahadasha lord's framing only for a chart with no such
        # extreme (see the "balanced chart" case surfaced below). Before this,
        # both fields were keyed to maha_key alone (only 9 possible values),
        # which is exactly why two unrelated charts could render identical
        # "brutal truth" text whenever they happened to share a current lord.
        framing = framing_pool.get(maha_key, framing_pool["Mo"])
        strength_framing = framing_pool.get(strongest_planet_key or maha_key, framing_pool["Mo"])
        challenge_framing = framing_pool.get(weakest_planet_key or maha_key, framing_pool["Mo"])

        names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
        focus = _FOCUS_BY_HOUSE_HI if language == "hi" else _FOCUS_BY_HOUSE_EN
        qualifier = _DIGNITY_QUALIFIER_HI if language == "hi" else _DIGNITY_QUALIFIER_EN

        # A real per-chart fact: which classical planet, if any, is
        # exalted/own-signed or debilitated in THIS chart. Many charts have
        # neither — that's not a bug, it's a chart with no extreme placements.
        if language == "hi":
            dignity_parts = []
            if strongest_planet_key:
                dignity_parts.append(f"सबसे मज़बूत ग्रह: {names[strongest_planet_key]}")
            if weakest_planet_key:
                dignity_parts.append(f"सबसे कमज़ोर ग्रह: {names[weakest_planet_key]}")
            dignity_line = (
                " · ".join(dignity_parts) if dignity_parts
                else "कोई भी ग्रह असामान्य रूप से मज़बूत या कमज़ोर स्थिति में नहीं है — यह एक संतुलित कुंडली है।"
            )
        else:
            dignity_parts = []
            if strongest_planet_key:
                dignity_parts.append(f"Strongest placement: {names[strongest_planet_key]}")
            if weakest_planet_key:
                dignity_parts.append(f"Most strained placement: {names[weakest_planet_key]}")
            dignity_line = (
                " · ".join(dignity_parts) if dignity_parts
                else "No planet sits in an unusually strong or weak position — a balanced chart, "
                     "not one built around a single dominant placement."
            )

        if language == "hi":
            timing_summary = f"{maha_name} महादशा फिलहाल आपके जीवन की मुख्य दिशा तय कर रही है।"
            if maha_house:
                timing_summary += f" {names[maha_key]} आपके {_hindi_house(maha_house)} में है और {qualifier[maha_dignity]}।"

            sections = {
                "personality_nature": {
                    "summary": (
                        f"आपका लग्न {lagna} है, जिसका स्वामी {names[lagna_lord_key]} आपके {_hindi_house(lagna_lord_house)} "
                        f"में है और {qualifier[lagna_lord_dignity]} — इसलिए आपका स्वभाव {focus[lagna_lord_house]} की "
                        "ओर झुकता है।"
                    ),
                    "key_points": [
                        f"लग्न स्वामी: {names[lagna_lord_key]}, भाव {lagna_lord_house}",
                        f"स्थिति: {qualifier[lagna_lord_dignity]}",
                    ],
                },
                "career_money": {
                    "summary": (
                        f"करियर भाव (10वां) के स्वामी {names[tenth_lord_key]} आपके {_hindi_house(tenth_lord_house)} में हैं "
                        f"और {qualifier[tenth_lord_dignity]}, जबकि फिलहाल चल रही {maha_name} महादशा भी इसी दिशा को "
                        "आकार दे रही है।"
                    ),
                    "key_points": [
                        f"करियर स्वामी: {names[tenth_lord_key]}, भाव {tenth_lord_house}",
                        "स्थिर प्रगति को प्राथमिकता दें, बड़े जोखिम से पहले दो बार सोचें",
                    ],
                },
                "relationships_marriage": {
                    "summary": (
                        f"रिश्तों के भाव (7वां) के स्वामी {names[seventh_lord_key]} आपके {_hindi_house(seventh_lord_house)} "
                        f"में हैं और {qualifier[seventh_lord_dignity]} — यही आपके रिश्तों के वास्तविक अनुभव की दिशा "
                        "तय करता है।"
                    ),
                    "key_points": [f"रिश्ते स्वामी: {names[seventh_lord_key]}, भाव {seventh_lord_house}"],
                },
                "health_temperament": {
                    "summary": (
                        f"स्वास्थ्य भाव (6ठा) के स्वामी {names[sixth_lord_key]} आपके {_hindi_house(sixth_lord_house)} "
                        f"में हैं और {qualifier[sixth_lord_dignity]} — नियमित दिनचर्या बनाए रखना आपके लिए फायदेमंद रहेगा।"
                    ),
                    "key_points": ["तनाव प्रबंधन पर ध्यान दें"],
                },
                "strengths_challenges": {
                    "summary": (
                        f"{_strip_trailing_stop(strength_framing['core_strength'])} आपकी शक्ति है; "
                        f"{_strip_trailing_stop(challenge_framing['core_challenge'])} आपकी चुनौती है।"
                    ),
                    "key_points": [
                        f"शक्ति: {strength_framing['core_strength']}",
                        f"चुनौती: {challenge_framing['core_challenge']}",
                        dignity_line,
                    ],
                },
                "timing_overview": {
                    "summary": timing_summary,
                    "key_points": ["बड़े फैसलों में जल्दबाज़ी न करें"],
                },
            }
        else:
            timing_summary = f"Your {maha_name} Mahadasha is currently the dominant force shaping your life direction."
            if maha_house:
                timing_summary += (
                    f" {names[maha_key]} sits in your {_ordinal(maha_house)} house, {qualifier[maha_dignity]}."
                )

            sections = {
                "personality_nature": {
                    "summary": (
                        f"Your Lagna is {lagna}, ruled by {names[lagna_lord_key]}. With {names[lagna_lord_key]} "
                        f"sitting in your {_ordinal(lagna_lord_house)} house — {qualifier[lagna_lord_dignity]} — "
                        f"your core personality leans toward {focus[lagna_lord_house]}."
                    ),
                    "key_points": [
                        f"Lagna lord: {names[lagna_lord_key]}, house {lagna_lord_house}",
                        f"Condition: {qualifier[lagna_lord_dignity]}",
                    ],
                },
                "career_money": {
                    "summary": (
                        f"Your career (10th house) is ruled by {names[tenth_lord_key]}, placed in your "
                        f"{_ordinal(tenth_lord_house)} house — {qualifier[tenth_lord_dignity]} — while your current "
                        f"{maha_name} Mahadasha shapes the broader direction."
                    ),
                    "key_points": [
                        f"Career lord: {names[tenth_lord_key]}, house {tenth_lord_house}",
                        "Favour steady progress over big swings",
                    ],
                },
                "relationships_marriage": {
                    "summary": (
                        f"Your relationships (7th house) are ruled by {names[seventh_lord_key]}, placed in your "
                        f"{_ordinal(seventh_lord_house)} house — {qualifier[seventh_lord_dignity]} — which shapes "
                        "how your relationships tend to actually play out."
                    ),
                    "key_points": [f"Relationship lord: {names[seventh_lord_key]}, house {seventh_lord_house}"],
                },
                "health_temperament": {
                    "summary": (
                        f"Your health (6th house) is ruled by {names[sixth_lord_key]}, placed in your "
                        f"{_ordinal(sixth_lord_house)} house — {qualifier[sixth_lord_dignity]} — a regular routine "
                        "works in your favour here."
                    ),
                    "key_points": ["Pay attention to stress management"],
                },
                "strengths_challenges": {
                    "summary": (
                        f"{_strip_trailing_stop(strength_framing['core_strength'])} is your strength; "
                        f"{_strip_trailing_stop(challenge_framing['core_challenge']).lower()} is your challenge."
                    ),
                    "key_points": [
                        f"Strength: {strength_framing['core_strength']}",
                        f"Challenge: {challenge_framing['core_challenge']}",
                        dignity_line,
                    ],
                },
                "timing_overview": {
                    "summary": timing_summary,
                    "key_points": ["Avoid rushing major decisions"],
                },
            }

        return {
            "sections": sections, "brutal_truth": framing["brutal_truth"],
            "core_strength": strength_framing["core_strength"], "core_challenge": challenge_framing["core_challenge"],
        }

    async def chat_reply(
        self, history: list[dict[str, str]], context: dict[str, Any], language: Language
    ) -> str:
        """Deterministic (no-LLM) free-text Q&A: matches the user's latest
        message against a small set of real-life topics/keywords and answers
        from facts already computed elsewhere in the app (house_breakdown,
        yogas/doshas, current dasha, today's reading) — never invents a
        fact the chart doesn't actually support.

        When context carries a rishi_id (see _RISHI_SPECIALTY), each Rishi
        only answers questions in their own specialty and redirects anything
        else to whichever Rishi actually owns it — Vasishtha won't answer a
        marriage question, Gargi won't answer a career one, etc. With no
        rishi_id (or an unrecognized one) every category is answered
        directly, matching the original persona-agnostic behaviour."""
        hi = language == "hi"
        lagna = context.get("lagna_sign", "")
        house_breakdown: dict[int, str] = context.get("house_breakdown", {})
        yogas: list[dict[str, str]] = context.get("yogas", [])
        daily: dict[str, Any] = context.get("daily_reading", {})
        mahadasha_lord = context.get("mahadasha_lord")
        antardasha_lord = context.get("antardasha_lord")
        rishi_id = context.get("rishi_id")

        message = history[-1]["content"].lower() if history else ""

        def asked_about(keywords: list[str]) -> bool:
            return any(k in message for k in keywords)

        category: str | None = None
        if asked_about(_TODAY_KEYWORDS):
            category = "today"
        elif message_mentions_marriage_timing(message):
            category = "marriage_timing"
        elif message_mentions_career_timing(message):
            category = "career_timing"
        elif message_mentions_wealth_timing(message):
            category = "wealth_timing"
        elif message_mentions_children_timing(message):
            category = "children_timing"
        elif message_mentions_foreign_travel_timing(message):
            category = "foreign_travel_timing"
        elif message_mentions_year_ahead(message):
            category = "year_ahead"
        elif asked_about(_DASHA_KEYWORDS):
            category = "dasha"
        elif asked_about(_DOSHA_KEYWORDS):
            category = "dosha"
        elif asked_about(_YOGA_KEYWORDS):
            category = "yoga"
        else:
            for topic in _TOPIC_HOUSE:
                if asked_about(_TOPIC_KEYWORDS[topic]):
                    category = topic
                    break

        out_of_scope = bool(category) and rishi_id in _RISHI_SPECIALTY and category not in _RISHI_SPECIALTY[rishi_id]

        answer: str | None = None
        if category == "today":
            parts = [daily.get("rating_reason"), daily.get("brutal_truth")]
            if daily.get("festival"):
                parts.append(f"आज {daily['festival']} है।" if hi else f"Today is {daily['festival']}.")
            answer = " ".join(p for p in parts if p) or None

        elif category == "marriage_timing":
            windows: list[dict[str, Any]] = context.get("marriage_timing_windows") or []
            if windows:
                top = windows[0]
                if hi:
                    answer = (
                        f"आपकी कुंडली के अनुसार, विवाह या किसी गंभीर साझेदारी के लिए सबसे संभावित समय "
                        f"{top['start_date']} से {top['end_date']} के बीच लगता है। {top['reason']} ध्यान रहे, यह एक "
                        "संभावित अनुकूल समय है, कोई निश्चित तारीख नहीं।"
                    )
                else:
                    answer = (
                        f"Based on your chart, the most likely window for marriage or a serious partnership looks "
                        f"like {top['start_date']} to {top['end_date']}. {top['reason']} Keep in mind this is a "
                        "probable favorable window, not a guaranteed exact date."
                    )
            else:
                answer = (
                    "मुझे अभी जितनी अवधि खोजी है उसमें कोई खास तौर पर अनुकूल समय नहीं मिला।"
                    if hi
                    else "I didn't find a strongly favorable window in the period I can currently search."
                )

        elif category in _LIFE_EVENT_CONTEXT_KEY:
            answer = _life_event_chat_answer(category, context, hi)

        elif category == "year_ahead":
            year_ahead: dict[str, Any] | None = context.get("year_ahead")
            if year_ahead:
                answer = (
                    f"{year_ahead['year']} के लिए, कुल रेटिंग {year_ahead['overall_rating']}/10 है। {year_ahead['overall_theme']}"
                    if hi
                    else f"For {year_ahead['year']}, the overall rating is {year_ahead['overall_rating']}/10. {year_ahead['overall_theme']}"
                )
                current_opportunity = year_ahead.get("current_quarter_opportunity")
                current_risk = year_ahead.get("current_quarter_risk")
                if current_opportunity:
                    answer += " " + (f"अभी के लिए: {current_opportunity}" if hi else f"Right now: {current_opportunity}")
                if current_risk:
                    answer += " " + (f"ध्यान रखें: {current_risk}" if hi else f"Watch out for: {current_risk}")

        elif category == "dasha" and mahadasha_lord and antardasha_lord:
            answer = (
                f"फिलहाल आपकी {mahadasha_lord} महादशा चल रही है, जिसके भीतर {antardasha_lord} की अंतर्दशा चल रही "
                "है — यही संयोजन इस समय आपके अनुभवों की मुख्य दिशा तय कर रहा है।"
                if hi
                else f"You're currently running your {mahadasha_lord} Mahadasha, with {antardasha_lord} Antardasha "
                "inside it — that combination is what's actually shaping this stretch of your life."
            )

        elif category == "dosha":
            findings = [y for y in yogas if y["key"] in _DOSHA_KEYS]
            if findings:
                answer = " ".join(f"{y['name']}: {y['description']}" for y in findings)
            else:
                answer = (
                    "आपकी कुंडली में मंगलिक, कालसर्प या केमद्रुम जैसा कोई प्रमुख दोष नहीं मिला।"
                    if hi
                    else "I didn't find Manglik, Kaal Sarp, or Kemadruma dosha in your chart."
                )

        elif category == "yoga":
            findings = [y for y in yogas if y["key"] not in _DOSHA_KEYS]
            if findings:
                answer = " ".join(f"{y['name']}: {y['description']}" for y in findings)
            else:
                answer = (
                    "आपकी कुंडली में कोई विशेष शास्त्रीय योग नहीं मिला — यह कमज़ोर कुंडली का संकेत नहीं है, कई मज़बूत "
                    "कुंडलियों में भी कोई नामी योग नहीं होता।"
                    if hi
                    else "I didn't detect a named classical yoga in your chart — that's not a sign of a weak chart, "
                    "plenty of strong charts don't carry one either."
                )

        elif category in _TOPIC_HOUSE:
            answer = house_breakdown.get(_TOPIC_HOUSE[category])

        if answer:
            # In-character lead-in before the real fact — a rotating choice
            # per Rishi (see _pick_variant) so the same question asked twice
            # doesn't come back as the identical line every time. Only
            # applied when a rishi_id is known; the persona-agnostic caller
            # (no rishi_id) gets the bare answer, unchanged.
            if rishi_id in _RISHI_LEAD_IN_EN:
                lead_in = _pick_variant(_RISHI_LEAD_IN_HI[rishi_id] if hi else _RISHI_LEAD_IN_EN[rishi_id], history)
                answer = f"{lead_in} {answer}"
            # A real, chart-grounded answer either way — out-of-specialty
            # questions still get the actual answer, just with a pointer to
            # whoever specializes in it for more depth, instead of a bare
            # refusal that leaves the user with nothing.
            return f"{answer} {_rishi_pointer(hi, category, history)}" if out_of_scope and category else answer

        if out_of_scope and category:
            # No real data exists for this category at all (e.g. no current
            # dasha on file) — nothing to answer with, so this is the one
            # case that's a pure redirect.
            return _rishi_refusal(hi, rishi_id, category)

        if rishi_id in _RISHI_FALLBACK_EN:
            return _pick_variant(_RISHI_FALLBACK_HI[rishi_id] if hi else _RISHI_FALLBACK_EN[rishi_id], history)

        if hi:
            return (
                f"आपका लग्न {lagna} है। आप मुझसे करियर, शादी, पैसा, सेहत, परिवार, दशा या आज के दिन के बारे में पूछ "
                "सकते हैं — जैसे \"मेरा करियर कैसा रहेगा\" या \"क्या मैं मंगलिक हूं\"।"
            )
        return (
            f"Your Lagna is {lagna}. You can ask me about career, marriage, money, health, family, your current "
            "dasha, or today — for example \"how's my career looking\" or \"am I manglik\"."
        )
