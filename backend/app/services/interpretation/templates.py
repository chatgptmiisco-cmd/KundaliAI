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
from datetime import date, datetime, timezone
from typing import Any, Literal

from rapidfuzz.distance import DamerauLevenshtein

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
    "exalted": "working exceptionally well",
    "debilitated": "struggling",
    "own_sign": "strong and comfortable",
    "neutral": "in an average, unremarkable position",
}
_DIGNITY_QUALIFIER_HI = {
    "exalted": "बहुत अच्छी स्थिति में है",
    "debilitated": "संघर्ष में है",
    "own_sign": "मज़बूत और सहज स्थिति में है",
    "neutral": "सामान्य, साधारण स्थिति में है",
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

# Every keyword list below is matched through this, not a bare `in` check —
# plain substring matching already produced two real false positives in this
# file: bare "ill" (health) is a substring of the extremely common word
# "will" ("when WILL I..."), and a bare "kid" (children) would be a substring
# of "kidney" or "kidding". \b-bounded matching structurally prevents that
# whole class of accidental match, for every keyword, not just the ones
# caught so far — so short/common keywords can be added freely without
# manually re-auditing every existing word for collisions each time.
# Multi-word phrases ("when will", "settle abroad") and non-Latin (Devanagari)
# keywords fall back to plain substring matching: \b doesn't reliably bound
# non-ASCII scripts in Python's `re`, and a phrase's own internal spaces
# already act as a boundary.
_KEYWORD_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    pattern = _KEYWORD_PATTERN_CACHE.get(keyword)
    if pattern is None:
        if " " in keyword or any(ord(c) > 0x2FF for c in keyword):
            pattern = re.compile(re.escape(keyword))
        else:
            pattern = re.compile(r"\b" + re.escape(keyword) + r"\b")
        _KEYWORD_PATTERN_CACHE[keyword] = pattern
    return pattern


# --- Typo/spelling-variant tolerance (Latin-script keywords) ---------------
# Real Hinglish has no fixed spelling ("shaadi"/"shadi"/"shadhi" are all the
# same word to a human), and plain typos happen too ("marraige"). Exact
# word-boundary matching alone silently misses both — this adds a small
# edit-distance fallback so a keyword also matches a message word that's
# just 1-2 characters off, without needing every spelling variant hand-
# written. Uses rapidfuzz (a real, maintained fuzzy-matching library, C++
# backed) instead of a hand-rolled distance function — specifically its
# Damerau-Levenshtein distance, which (unlike plain Levenshtein) counts an
# adjacent-letter transposition as ONE edit instead of two, so "marraige"
# (transposed i/a) now matches "marriage" at distance 1 instead of 2. Scoped
# to LATIN-script keywords only: Devanagari typo patterns are a different,
# script-specific problem this doesn't attempt to solve.
_WORD_TOKEN_RE = re.compile(r"[a-z]+")


def _message_word_tokens(message: str) -> list[str]:
    return _WORD_TOKEN_RE.findall(message.lower())


def _fuzzy_max_distance(keyword_length: int) -> int:
    """How many edits a message word may be from a keyword and still count
    as a match, scaled to the keyword's own length — a fixed distance would
    either let a short keyword match almost anything, or refuse to fuzz a
    long word at all. 0 means "exact only" (too short to fuzz safely even
    with the same-first-letter guard in _fuzzy_word_matches_keyword: a
    3-letter keyword like "din" turned out to be edit-distance 1 from both
    the common word "in" AND from "did" — another keyword in this very file
    — even after requiring a matching first letter). Genuinely common short
    variants (like "kab" -> "kb") are handled as an explicit literal keyword
    instead of generic fuzzing."""
    if keyword_length <= 3:
        return 0
    if keyword_length <= 5:
        return 1
    return 2


# Two real, distinct astrology keyword FAMILIES ("dasha"/"dashas" and
# "dosha"/"doshas") that all sit at edit-distance 1 of their singular/plural
# counterpart across families (dasha<->dosha, dashas<->doshas) and distance
# 2 across the rest (dasha<->doshas, dashas<->dosha, within this 6-letter
# bucket's own tolerance) — the generic length-based bucket alone would
# fuzzy-match a real "dasha" question against the unrelated "dosha" keyword,
# wrongly also answering a dosha question no one asked (caught live: a
# plain "what dasha am I running" reply picked up an unrelated Manglik
# dosha finding). Exact-only for all four, the same fix already applied to
# "din"/"did"/"in" above.
_NO_FUZZY_KEYWORDS = {"dasha", "dashas", "dosha", "doshas"}


def _fuzzy_word_matches_keyword(word: str, keyword: str) -> bool:
    if keyword in _NO_FUZZY_KEYWORDS:
        return word == keyword
    max_distance = _fuzzy_max_distance(len(keyword))
    if max_distance == 0:
        return word == keyword
    if abs(len(word) - len(keyword)) > max_distance:
        return False  # cheap reject before the distance computation
    # A real typo/spelling variant almost never changes a word's FIRST
    # letter — this single constraint is what stops a short keyword from
    # fuzzy-matching an unrelated common word that merely happens to be
    # nearby in edit-distance (e.g. "din" — a today/day keyword — matching
    # the extremely common word "in" at distance 1 before this was added,
    # which wrongly classified almost every message as a "today" question).
    if word[:1] != keyword[:1]:
        return False
    return DamerauLevenshtein.distance(word, keyword, score_cutoff=max_distance) <= max_distance


def _fuzzy_contains_keyword(message_words: list[str], keyword: str) -> bool:
    return any(_fuzzy_word_matches_keyword(word, keyword) for word in message_words)


def _fuzzy_contains_phrase(message_words: list[str], phrase_words: list[str]) -> bool:
    """A multi-word Latin phrase ("sarkari naukri", "green card") matches
    when EVERY one of its words is found somewhere in the message — each
    checked with the same exact-or-fuzzy single-word matcher as above — so
    a typo inside any one word of the phrase ("sarkari nokri kab lagegi")
    is tolerated too, not just single-word keywords. Order isn't required:
    real questions reorder phrase words often enough ("naukri sarkari wali
    kab milegi") that requiring the exact sequence would undo the point of
    fuzzing in the first place."""
    return all(
        any(w == pw or _fuzzy_word_matches_keyword(w, pw) for w in message_words) for pw in phrase_words
    )


def _contains_any_keyword(message: str, keywords: list[str]) -> bool:
    message_words: list[str] | None = None
    for k in keywords:
        if _keyword_pattern(k).search(message):
            return True
        is_devanagari = any(ord(c) > 0x2FF for c in k)
        if is_devanagari:
            continue
        if message_words is None:
            message_words = _message_word_tokens(message)
        if " " in k:
            if _fuzzy_contains_phrase(message_words, k.split(" ")):
                return True
        elif _fuzzy_contains_keyword(message_words, k):
            return True
    return False


_TOPIC_HOUSE: dict[str, int] = {
    "career": 10, "money": 2, "marriage": 7, "health": 6, "family": 4,
    "education": 9, "friends": 11, "travel": 9, "children": 5, "siblings": 3,
}
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    # Each list is deliberately over-inclusive with common inflections
    # (jobs/hiring, married/marrying, financial/financially) rather than
    # relying on the reader to remember every derived form — plain substring
    # matching has already missed "married" (not inside "marry") and
    # "financial" (not inside "finance") once each in practice, so this pass
    # closes that whole bug class instead of patching one word at a time.
    "career": [
        "career", "careers", "job", "jobs", "hiring", "hired", "profession", "professional",
        "promotion", "promoted", "business", "employment", "employed", "unemployed",
        # Government-job phrasing ("sarkari naukri kab lagegi") is extremely
        # high-volume in Indian astrology specifically and was entirely
        # missing before this — real FAQ research surfaced it as one of the
        # single most common question categories.
        "sarkari naukri", "government job", "govt job", "ias", "ips", "civil services",
        "bank job", "posting",
        "naukri", "karobar", "नौकरी", "करियर", "पेशा", "व्यापार", "प्रमोशन", "सरकारी नौकरी",
    ],
    "money": [
        "money", "finance", "finances", "financial", "financially", "wealth", "wealthy",
        "income", "salary",
        # Loans/debt/investment are all facets of the same classical
        # dhana (wealth) significations already computed for this topic
        # (2nd/11th house + Jupiter/Venus dasha) — not a new domain, just
        # more of the real ways people actually phrase a money question.
        "loan", "loans", "debt", "debts", "invest", "investing", "investment", "investments",
        "paisa", "paise", "dhan", "karza", "nivesh",
        "पैसा", "पैसे", "धन", "आर्थिक", "वित्त", "वित्तीय", "कर्ज़", "कर्ज", "निवेश", "ऋण",
    ],
    "marriage": [
        "marriage", "marriages", "marry", "married", "marrying", "shaadi", "vivah",
        "husband", "wife", "spouse", "partner", "engaged", "engagement", "fiance", "fiancé", "fiancée",
        "शादी", "विवाह", "पति", "पत्नी", "जीवनसाथी", "सगाई",
    ],
    "health": [
        # Deliberately NOT bare "ill" — it's a substring of the extremely
        # common word "will" ("when WILL I...") and matched almost every
        # timing question by accident; "illness"/"illnesses" alone are
        # distinctive enough to keep without that collision risk.
        "health", "healthy", "sick", "sickness", "illness", "illnesses", "disease", "diseases",
        # Operations/accidents are real, high-volume health-house questions
        # ("will I need surgery", "accident hone ka dar hai") — same 6th-house
        # static reading this topic already answers with, not a new domain.
        "operation", "operations", "surgery", "surgeries", "accident", "accidents", "injury", "injuries",
        "tabiyat", "durghatna", "chot",
        "सेहत", "स्वास्थ्य", "बीमारी", "बीमार", "तबीयत", "ऑपरेशन", "सर्जरी", "दुर्घटना", "चोट",
    ],
    "family": [
        "family", "families", "parents", "parent", "mother", "father", "ghar",
        # Property/vehicle are classical 4th-house significations (home,
        # land, conveyance, domestic comfort) alongside "family" — same
        # house this topic already reads from, just more of the real
        # questions people ask about it. Deliberately NOT bare "house"/
        # "home": "house" collides with "which house is my Saturn in"
        # (the astrological sense), and both are already covered by "ghar".
        "property", "properties", "ancestral property", "vehicle", "vehicles", "car", "cars",
        "sampatti", "vahan",
        "परिवार", "माता", "पिता", "घर", "संपत्ति", "जायदाद", "वाहन", "गाड़ी",
    ],
    "education": [
        "study", "studies", "studying", "studied", "education", "educational", "exam", "exams",
        "competitive exam", "clear the exam", "board exam", "college admission",
        "padhai", "पढ़ाई", "शिक्षा", "परीक्षा", "बोर्ड परीक्षा", "कॉलेज एडमिशन",
    ],
    "friends": ["friend", "friends", "friendship", "dost", "दोस्त", "मित्र", "दोस्ती"],
    "travel": [
        "travel", "travels", "travelling", "traveling", "trip", "trips", "abroad", "videsh", "safar",
        "यात्रा", "विदेश", "सफर",
    ],
    "children": [
        "child", "children", "kid", "kids", "baby", "babies", "childbirth", "santan",
        "औलाद", "संतान", "बच्च", "बच्चे",
    ],
    "siblings": [
        "sibling", "siblings", "brother", "brothers", "sister", "sisters", "bhai", "behen",
        "भाई", "बहन",
    ],
}
_DOSHA_KEYS = {"manglik", "kaal_sarp", "kemadruma"}
_DOSHA_KEYWORDS = [
    "dosha", "doshas", "dosh", "manglik", "mangalik", "mangal dosh", "kaal sarp", "kaalsarp", "kemadruma",
    # Sade Sati and Dhaiya are the other two classically-named dosha-like
    # hardship windows this app computes (see daily_reading_service's
    # doshas list) — real questions asking about them by name specifically
    # must reach the same "dosha" category, not fall through to a generic
    # fallback that never mentions either.
    "sade sati", "sadhesati", "dhaiya", "kantak shani",
    "दोष", "मंगलिक", "कालसर्प", "काल सर्प", "केमद्रुम", "साढ़े साती", "साढ़ेसाती", "ढैया", "कंटक शनि",
]
_YOGA_KEYWORDS = ["yoga", "yogas", "raj yoga", "gajakesari", "mahapurusha", "योग"]
_DASHA_KEYWORDS = [
    "dasha", "dashas", "mahadasha", "antardasha", "pratyantardasha", "period", "when will", "kab", "कब",
    "दशा", "महादशा", "अंतर्दशा",
]
_TODAY_KEYWORDS = ["today", "todays", "today's", "aaj", "आज", "daily", "din"]

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
    # "kb" (vowel-dropped "kab") is extremely common in casual Hinglish
    # texting — added as its own literal rather than relying on generic
    # fuzzing, since 3-letter keywords are excluded from fuzzy matching
    # entirely (see _fuzzy_max_distance) as too collision-prone.
    "kb",
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


def _has_timing_signal(lowered_message: str) -> bool:
    """True for either a forward-looking timing hint ("when", "kab", "will
    i") or a past-tense marker ("was", "did", "happened") — a real timing
    question can be asked about the future OR the past ("when will I get
    married" / "why WAS my marriage delayed"), and both need the actual
    Prediction Engine rather than a static topic answer. Without this, a
    past-tense timing question silently fell through to the plain topic
    text since it never contained a future-oriented hint at all."""
    return _contains_any_keyword(lowered_message, _TIMING_HINT_KEYWORDS) or message_mentions_past_tense(
        lowered_message
    )


def message_mentions_marriage_timing(message: str) -> bool:
    """True for a real WHEN-will-I-get-married question — the caller (see
    app.api.v1.chat) uses this to decide whether to fetch the marriage-timing
    engine's output at all, avoiding that computation on unrelated chat
    messages."""
    lowered = message.lower()
    has_marriage = _contains_any_keyword(lowered, _TOPIC_KEYWORDS["marriage"])
    return has_marriage and _has_timing_signal(lowered)


def message_mentions_year_ahead(message: str) -> bool:
    """True for a real how's-my-year-going question — used the same way as
    message_mentions_marriage_timing above."""
    lowered = message.lower()
    if _YEAR_TOKEN_RE.search(lowered):
        return True
    return _contains_any_keyword(lowered, _YEAR_AHEAD_PHRASES)


# Same pattern as marriage timing, generalized to career/wealth/children —
# reuse the existing topic keyword lists, ANDed with the same timing hint,
# so a plain non-timing topic question ("what career suits me?") still gets
# the existing static house-text answer, unchanged.
def message_mentions_career_timing(message: str) -> bool:
    lowered = message.lower()
    has_career = _contains_any_keyword(lowered, _TOPIC_KEYWORDS["career"])
    return has_career and _has_timing_signal(lowered)


def message_mentions_wealth_timing(message: str) -> bool:
    lowered = message.lower()
    has_money = _contains_any_keyword(lowered, _TOPIC_KEYWORDS["money"])
    return has_money and _has_timing_signal(lowered)


def message_mentions_children_timing(message: str) -> bool:
    lowered = message.lower()
    has_children = _contains_any_keyword(lowered, _TOPIC_KEYWORDS["children"])
    return has_children and _has_timing_signal(lowered)


# Deliberately its own keyword list, not the generic "travel" topic (trip/
# safar/etc., which stays a plain 9th-house answer) — a genuine foreign-
# relocation question needs the life-event engine, an ordinary domestic-trip
# question doesn't.
_FOREIGN_TRAVEL_KEYWORDS = [
    "abroad", "foreign country", "foreign", "immigrate", "immigrating", "immigration",
    "emigrate", "emigrating", "settle abroad", "settling abroad", "move overseas", "moving overseas",
    "relocate abroad", "relocating abroad",
    # "pr" (permanent residency) and "visa" are real, extremely common
    # phrasing per FAQ research ("PR milega kya", "visa kab tak lagega") —
    # both word-boundary matched, so "visa" doesn't wrongly fire inside
    # "advisable" and "pr" only matches as its own standalone token.
    "pr", "visa", "green card", "h1b",
    "videsh", "pravas", "विदेश", "प्रवास",
]


def message_mentions_foreign_travel_timing(message: str) -> bool:
    lowered = message.lower()
    has_foreign = _contains_any_keyword(lowered, _FOREIGN_TRAVEL_KEYWORDS)
    return has_foreign and _has_timing_signal(lowered)


def message_mentions_relocation_decision(message: str) -> bool:
    # Reuses the SAME keyword list as foreign_travel_timing above — what
    # distinguishes "should I relocate" (a decision, routes to
    # relocation_decision) from "when will I get to move abroad"
    # (foreign_travel_timing) is purely the decision-signal ("should I..."),
    # not a different vocabulary; _has_decision_signal is defined further
    # below in this module.
    lowered = message.lower()
    has_foreign = _contains_any_keyword(lowered, _FOREIGN_TRAVEL_KEYWORDS)
    return has_foreign and _has_decision_signal(lowered)


# --- Phase 2 sub-intents (career_promotion/business_partnership/
# business_expansion) — deliberately their own keyword lists, checked
# ALONGSIDE (not instead of) the generic "career" topic above, which
# already contains "promotion"/"business" itself: a message can and often
# does match both, and app.api.v1.chat fetches every category that
# matches rather than picking one, so the LLM just gets both the generic
# career_timing AND the more specific sub-intent's windows to choose from.
_CAREER_PROMOTION_KEYWORDS = ["promotion", "promoted", "raise", "pay rise", "पदोन्नति", "प्रमोशन"]
_BUSINESS_EXPANSION_KEYWORDS = [
    "expand", "expansion", "grow my business", "scale my business", "new branch",
    "business badhana", "business ko badhana",
    "व्यापार का विस्तार", "व्यवसाय बढ़ाना",
]
_BUSINESS_PARTNERSHIP_KEYWORDS = [
    "business partner", "co-founder", "cofounder", "partnership",
    "व्यापारिक साझेदारी", "साझेदार",
]


def message_mentions_career_promotion_timing(message: str) -> bool:
    lowered = message.lower()
    return _contains_any_keyword(lowered, _CAREER_PROMOTION_KEYWORDS) and _has_timing_signal(lowered)


def message_mentions_business_expansion_timing(message: str) -> bool:
    # Accepts a decision-style signal too ("should I expand my business
    # now?"), not just a "when" timing signal — real business-expansion
    # questions are phrased as often one way as the other, and either one
    # genuinely calls for the same business_expansion windows.
    lowered = message.lower()
    has_expansion = _contains_any_keyword(lowered, _BUSINESS_EXPANSION_KEYWORDS)
    return has_expansion and (_has_timing_signal(lowered) or _has_decision_signal(lowered))


def message_mentions_business_partnership_timing(message: str) -> bool:
    lowered = message.lower()
    has_partnership = _contains_any_keyword(lowered, _BUSINESS_PARTNERSHIP_KEYWORDS)
    return has_partnership and (_has_timing_signal(lowered) or _has_decision_signal(lowered))


# --- Phase 3 decision support ("should I do X now?") ----------------------
# A decision question needs its own signal, distinct from _has_timing_signal
# ("when will X happen") — "should I switch jobs" isn't asking when, it's
# asking whether now is a good idea, which routes to
# prediction_service.get_decision instead of a timing window scan.
_DECISION_SIGNAL_KEYWORDS = [
    "should i", "should we", "is it a good idea", "is this a good idea",
    "क्या मुझे", "kya mujhe",
]
_JOB_CHANGE_DECISION_KEYWORDS = [
    "switch jobs", "switch my job", "change jobs", "change my job", "quit my job", "leave my job",
    "naukri badal", "job badal",
    "नौकरी बदल", "जॉब बदल",
]
_BUSINESS_START_DECISION_KEYWORDS = [
    "start a business", "start my own business", "start my business",
    "business shuru", "apna business shuru",
    "व्यवसाय शुरू", "बिज़नेस शुरू",
]


def _has_decision_signal(lowered_message: str) -> bool:
    return _contains_any_keyword(lowered_message, _DECISION_SIGNAL_KEYWORDS)


def message_mentions_job_change_decision(message: str) -> bool:
    lowered = message.lower()
    return _contains_any_keyword(lowered, _JOB_CHANGE_DECISION_KEYWORDS) and _has_decision_signal(lowered)


def message_mentions_business_start_decision(message: str) -> bool:
    lowered = message.lower()
    return _contains_any_keyword(lowered, _BUSINESS_START_DECISION_KEYWORDS) and _has_decision_signal(lowered)


# Phase 5: no existing "house"/"property" topic keyword list anywhere in
# this file (confirmed — nothing else in the app talks about property at
# all) — this is the first and only one, purely for detecting the
# house_purchase_decision category.
_HOUSE_PURCHASE_KEYWORDS = [
    "buy a house", "buying a house", "buy a home", "buying a home", "purchase a house", "purchasing a house",
    "buy property", "buying property", "ghar khareed", "makaan khareed",
    "घर खरीद", "मकान खरीद", "प्रॉपर्टी खरीद",
]


def message_mentions_house_purchase_decision(message: str) -> bool:
    lowered = message.lower()
    return _contains_any_keyword(lowered, _HOUSE_PURCHASE_KEYWORDS) and _has_decision_signal(lowered)


def message_mentions_marriage_decision(message: str) -> bool:
    # Reuses the SAME keyword list as the plain "marriage" topic/marriage_
    # timing — what distinguishes "should I get married now" (a decision)
    # from "tell me about my marriage" (the plain topic) or "when will I
    # get married" (marriage_timing) is purely the decision-signal
    # ("should I..."), not a different vocabulary — same pattern as
    # message_mentions_relocation_decision reusing foreign_travel's list.
    lowered = message.lower()
    has_marriage = _contains_any_keyword(lowered, _TOPIC_KEYWORDS["marriage"])
    return has_marriage and _has_decision_signal(lowered)


# Phase 9 — property_sale/property_inheritance/property_relocation reuse
# the SAME BPHS 48.2-4 signal house_purchase_decision already does (see
# app.astro.property_analysis), reinterpreted by intent — each gets its own
# keyword list since "sell"/"inherit"/"move house" are genuinely distinct
# vocabulary, not shared with _HOUSE_PURCHASE_KEYWORDS above.
_PROPERTY_SALE_KEYWORDS = [
    "sell my house", "selling my house", "sell my home", "selling my home", "sell my property",
    "selling my property", "sell my land", "ghar bech", "makaan bech", "property bech",
    "घर बेच", "मकान बेच", "संपत्ति बेच",
]
_PROPERTY_INHERITANCE_KEYWORDS = [
    "inherit property", "inherit a house", "inherit land", "inheritance of property",
    "ancestral property", "ancestral home", "parivarik sampatti", "poojiwali zameen",
    "विरासत में संपत्ति", "पैतृक संपत्ति", "पैतृक घर",
]
# Deliberately distinct from _FOREIGN_TRAVEL_KEYWORDS (country/abroad
# vocabulary, used by relocation_decision — Phase 3, the 12th house) — this
# is about moving HOMES, a 4th-house matter, not moving countries.
_PROPERTY_RELOCATION_KEYWORDS = [
    "move house", "moving house", "move homes", "moving homes", "change my residence",
    "changing my residence", "change residence", "shift house", "shifting house", "ghar badal",
    "makaan badal", "घर बदल", "मकान बदल", "निवास बदल",
]


def message_mentions_property_sale(message: str) -> bool:
    lowered = message.lower()
    return _contains_any_keyword(lowered, _PROPERTY_SALE_KEYWORDS) and (
        _has_timing_signal(lowered) or _has_decision_signal(lowered)
    )


def message_mentions_property_inheritance(message: str) -> bool:
    lowered = message.lower()
    return _contains_any_keyword(lowered, _PROPERTY_INHERITANCE_KEYWORDS) and (
        _has_timing_signal(lowered) or _has_decision_signal(lowered)
    )


def message_mentions_property_relocation(message: str) -> bool:
    lowered = message.lower()
    return _contains_any_keyword(lowered, _PROPERTY_RELOCATION_KEYWORDS) and (
        _has_timing_signal(lowered) or _has_decision_signal(lowered)
    )


# --- Past-event reflection: tense detection + a target-date resolver ------
# "Why did my marriage get delayed", "what happened to me around 2016",
# "why was 28 such a hard year" — real astrologers narrate the PAST from the
# same Dasha+transit engine used for future timing, just pointed backward
# (see app.services.prediction_service.get_life_theme and the `direction`
# parameter on get_marriage_timing/get_life_event_timing). This is the NLU
# layer that recognizes a past-tense question and — when possible — resolves
# WHICH past date it's actually asking about.
_PAST_TENSE_KEYWORDS = [
    "did i", "did my", "was there", "was my", "happened", "why did", "used to",
    "back then", "in the past", "ago",
    "hua tha", "hui thi", "pehle", "kya hua",
    "क्या हुआ", "पहले", "हुआ था", "हुई थी",
]


def message_mentions_past_tense(message: str) -> bool:
    return _contains_any_keyword(message.lower(), _PAST_TENSE_KEYWORDS)


# Matches ONLY when the entire message is a bare greeting — "hi", "namaste!",
# "hello ji", repeated letters ("hiii"/"helloo") and all included — so a real
# question that happens to start with a greeting ("hi, how's my career?")
# still goes through normal classification and is never short-circuited here.
_GREETING_RE = re.compile(
    r"^(hi+|he+llo+|hey+|yo+|namaste+|namaskaram?|namastey|pranam|"
    r"good\s?(?:morning|afternoon|evening)|gm|ge|salaam|assalam[u]?\s?alaikum|hola)"
    r"\s*(?:ji)?[\s!.,~]*$",
    re.IGNORECASE,
)


def message_is_greeting(message: str) -> bool:
    return bool(_GREETING_RE.match(message.strip()))


# A short yes/no reply ("yes", "haan bilkul", "nahi abhi nahi") — used to
# deterministically resolve a plain yes/no question this app itself just
# asked (see chat.py's career-employment gate reply handling) on the
# fallback (no-LLM) path, where there's otherwise no way at all to turn a
# bare "yes" into a life-state fact. Anchored at the start with a word
# boundary so "yesterday"/"nobody" don't false-match, but still matches a
# longer reply that OPENS with the yes/no word ("yeah I am").
_AFFIRMATIVE_RE = re.compile(r"^(yes+|yeah+|yep+|yup+|haan+|han)\b", re.IGNORECASE)
_NEGATIVE_RE = re.compile(r"^(nope+|no+|nahi+n?|nah)\b", re.IGNORECASE)


def message_is_affirmative_reply(message: str) -> bool:
    return bool(_AFFIRMATIVE_RE.match(message.strip()))


def message_is_negative_reply(message: str) -> bool:
    return bool(_NEGATIVE_RE.match(message.strip()))


# Matches a real calendar year anywhere from a plausible birth year (1900)
# through the current one — deliberately wider than _YEAR_TOKEN_RE above
# (which only covers 2020-2049, tuned for near-future "how's my year"
# questions), since a past reference can point decades further back.
_EXPLICIT_PAST_YEAR_RE = re.compile(r"\b(19\d{2}|20[0-4]\d)\b")
_YEARS_AGO_RE = re.compile(r"\b(\d{1,2})\s*(?:years?|saal|sal|साल)\s*(?:ago|pehle|पहले)\b")
_WHEN_I_WAS_AGE_RE = re.compile(r"\b(?:when i was|at age|umar (?:thi|the)?)\s*(\d{1,2})\b")


def resolve_past_reference(message: str, birth_year: int, current_year: int) -> date | None:
    """Parses an explicit year, "N years ago", or "when I was N" (age) into
    a representative (mid-year) date — the real, resolvable date a past
    question is actually asking about. Returns None rather than guessing
    when nothing in the message pins down a specific date; callers should
    fall through to existing behavior in that case, not fabricate one."""
    lowered = message.lower()

    explicit = _EXPLICIT_PAST_YEAR_RE.search(lowered)
    if explicit:
        year = int(explicit.group())
        if birth_year <= year <= current_year:
            return date(year, 7, 1)

    ago_match = _YEARS_AGO_RE.search(lowered)
    if ago_match:
        year = current_year - int(ago_match.group(1))
        if birth_year <= year <= current_year:
            return date(year, 7, 1)

    age_match = _WHEN_I_WAS_AGE_RE.search(lowered)
    if age_match:
        year = birth_year + int(age_match.group(1))
        if birth_year <= year <= current_year:
            return date(year, 7, 1)

    return None


# Shared reply formatter for every timing category (marriage + the 4
# life-events) — surfaces ALL of the computed windows, not just the top
# one, with a short line per secondary window plus a real "most likely age"
# estimate (derived directly from the top window's own start/end year, not
# invented) and an honest caveat. Chat bubbles render as plain RN <Text>
# with no markdown parser (see RishiChatScreen) — so structure here comes
# from real line breaks and a numbered list, never "**bold**"/"##" syntax,
# which would just show up as literal asterisks/hashes on screen.
#
# Built after live feedback that comparing our single-line answer against
# ChatGPT/Perplexity's multi-window, age-estimate, caveat-carrying replies
# made ours look both less informative AND harder to read — even though
# every fact here was already being computed, most of it just wasn't being
# shown.
def _format_timing_reply(
    windows: list[dict[str, Any]], label: str, direction: str, birth_year: int | None, hi: bool
) -> str:
    if not windows:
        if direction == "past":
            return (
                f"मुझे उस समय की अवधि में {label} से जुड़ा कोई खास तौर पर सक्रिय दौर नहीं दिखा।"
                if hi
                else f"I didn't find a strongly active window for {label} in that past period of your chart."
            )
        return (
            "मुझे अभी जितनी अवधि खोजी है उसमें कोई खास तौर पर अनुकूल समय नहीं मिला।"
            if hi
            else "I didn't find a strongly favorable window in the period I can currently search."
        )

    top = windows[0]
    secondary = windows[1:]

    def _secondary_line_en(w: dict[str, Any]) -> str:
        corrob = ", with a transit confirming it" if w["transit_corroborated"] else ""
        return f"{w['start_date']} to {w['end_date']} — also under a period led by {w['antardasha_lord_name']}{corrob}."

    def _secondary_line_hi(w: dict[str, Any]) -> str:
        corrob = ", और गोचर भी इसकी पुष्टि करता है" if w["transit_corroborated"] else ""
        return f"{w['start_date']} से {w['end_date']} — यह भी {w['antardasha_lord_name']} के नेतृत्व वाली अवधि में आता है{corrob}।"

    if hi:
        if direction == "past":
            lead = f"आपकी कुंडली के अनुसार, {label} के लिए सबसे संभावित दौर {top['start_date']} से {top['end_date']} के बीच था।"
        else:
            lead = f"आपकी कुंडली के अनुसार, {label} के लिए सबसे संभावित समय {top['start_date']} से {top['end_date']} के बीच लगता है।"
        lines = [lead, top["reason"]]
        if secondary:
            lines.append("")
            lines.append("अन्य संभावित दौर:")
            for i, w in enumerate(secondary, start=2):
                lines.append(f"{i}. {_secondary_line_hi(w)}")
        if direction == "future" and birth_year is not None:
            age_low = int(top["start_date"][:4]) - birth_year
            age_high = int(top["end_date"][:4]) - birth_year
            lines.append("")
            age_text = f"लगभग {age_low} वर्ष" if age_low == age_high else f"लगभग {age_low}–{age_high} वर्ष"
            lines.append(f"सबसे संभावित उम्र: {age_text}, सबसे मजबूत दौर के आधार पर।")
        lines.append("")
        if direction == "past":
            lines.append("क्या यह उस समय आपके जीवन में हुई किसी बात से मेल खाता है?")
        else:
            lines.append(
                "ध्यान रहे: यह आपकी दशा और गोचर के आधार पर एक संभावित अनुकूल समय है, कोई निश्चित तारीख नहीं — और जन्म-समय "
                "की सटीकता मायने रखती है, क्योंकि कुछ मिनटों का अंतर भी यह गणना बदल सकता है।"
            )
        return "\n".join(lines)

    if direction == "past":
        lead = f"Based on your chart, the most likely window for {label} was {top['start_date']} to {top['end_date']}."
    else:
        lead = f"Based on your chart, the most likely window for {label} looks like {top['start_date']} to {top['end_date']}."
    lines = [lead, top["reason"]]
    if secondary:
        lines.append("")
        lines.append("Other windows worth knowing about:")
        for i, w in enumerate(secondary, start=2):
            lines.append(f"{i}. {_secondary_line_en(w)}")
    if direction == "future" and birth_year is not None:
        age_low = int(top["start_date"][:4]) - birth_year
        age_high = int(top["end_date"][:4]) - birth_year
        lines.append("")
        age_text = f"around {age_low}" if age_low == age_high else f"around {age_low}–{age_high}"
        lines.append(f"Most likely age: {age_text}, based on the strongest window above.")
    lines.append("")
    if direction == "past":
        lines.append("Does that line up with anything that happened for you around then?")
    else:
        lines.append(
            "Keep in mind: this is a probable favorable window based on your dasha and transits, not a "
            "guaranteed exact date — and birth-time accuracy matters, since even a few minutes' difference can "
            "shift these calculations."
        )
    return "\n".join(lines)


# Shared chat-answer composer for the 4 life-event-timing categories — same
# "top window + reason, or an honest no-window-found line" shape as the
# marriage_timing branch below, factored out once instead of repeated 4x
# since (unlike marriage) these have no bespoke copy of their own.
_LIFE_EVENT_LABEL_EN: dict[str, str] = {
    "career_timing": "a career or job change",
    "wealth_timing": "your financial growth",
    "children_timing": "having a child",
    "foreign_travel_timing": "foreign travel or relocation",
    "career_promotion_timing": "a promotion",
    "business_expansion_timing": "expanding your business",
    "business_partnership_timing": "a business partnership",
    # relocation_decision reuses the same foreign_travel signal as
    # foreign_travel_timing above (see chat.py) — its own label reads as a
    # decision ("should you relocate"), not a timing question ("when will
    # you travel"), even though both draw on the identical windows.
    "relocation_decision": "whether now is a good window to relocate",
}
_LIFE_EVENT_LABEL_HI: dict[str, str] = {
    "career_timing": "करियर या नौकरी में बदलाव",
    "wealth_timing": "आपकी आर्थिक वृद्धि",
    "children_timing": "संतान प्राप्ति",
    "foreign_travel_timing": "विदेश यात्रा या स्थानांतरण",
    "career_promotion_timing": "पदोन्नति",
    "business_expansion_timing": "आपके व्यवसाय का विस्तार",
    "business_partnership_timing": "व्यापारिक साझेदारी",
    "relocation_decision": "क्या अभी स्थानांतरण के लिए अच्छा समय है",
}
_LIFE_EVENT_CONTEXT_KEY: dict[str, str] = {
    "career_timing": "career_timing_windows",
    "wealth_timing": "wealth_timing_windows",
    "children_timing": "children_timing_windows",
    "foreign_travel_timing": "foreign_travel_timing_windows",
    "career_promotion_timing": "career_promotion_timing_windows",
    "business_expansion_timing": "business_expansion_timing_windows",
    "business_partnership_timing": "business_partnership_timing_windows",
    "relocation_decision": "relocation_decision_windows",
}
# When a life-event category's windows list comes back empty because of a
# LifeState gate (currently only business_partnership_timing — see
# prediction_service.get_life_event_timing), the context also carries a
# `{category}_note` explaining why, so the reply can say that honestly
# instead of "no window found" reading as though nothing matched at all.
_LIFE_EVENT_NOTE_CONTEXT_KEY: dict[str, str] = {
    "business_partnership_timing": "business_partnership_timing_note",
    "relocation_decision": "relocation_decision_note",
    "career_promotion_timing": "career_promotion_timing_note",
}


def _personal_pattern_sentence(category: str, context: dict[str, Any], hi: bool) -> str | None:
    """Phase 4 — spec's "richer correlations": a plain, deterministic
    sentence stating a real correlation in the user's OWN confirmed history
    (see life_pattern_service), never an interpretive claim, so this stays
    true and worth stating even on the template (non-LLM) path."""
    pattern = context.get(f"{category}_personal_pattern")
    if not pattern:
        return None
    lord, count = pattern.get("shared_mahadasha_lord"), pattern.get("shared_mahadasha_count")
    if not lord:
        lord, count = pattern.get("shared_antardasha_lord"), pattern.get("shared_antardasha_count")
    if not lord:
        return None
    if hi:
        return f"दिलचस्प बात यह है कि आपके इस क्षेत्र के {count} पिछले वाकये {lord} की अवधि में हुए हैं।"
    return f"Interestingly, {count} of your past events in this area happened during a {lord} period."


def _life_event_chat_answer(category: str, context: dict[str, Any], hi: bool) -> str:
    windows: list[dict[str, Any]] = context.get(_LIFE_EVENT_CONTEXT_KEY[category]) or []
    note_key = _LIFE_EVENT_NOTE_CONTEXT_KEY.get(category)
    if not windows and note_key and context.get(note_key):
        return context[note_key]
    label = (_LIFE_EVENT_LABEL_HI if hi else _LIFE_EVENT_LABEL_EN)[category]
    direction = context.get(f"{category}_direction", "future")
    birth_year = context.get("birth_year")
    reply = _format_timing_reply(windows, label, direction, birth_year, hi)
    pattern_sentence = _personal_pattern_sentence(category, context, hi)
    return f"{reply}\n\n{pattern_sentence}" if pattern_sentence else reply

# Which Rishi persona owns which question category — the specialization the
# user asked for ("Vasishtha only answers life direction, Parashara only
# timing, Gargi only relationships") rather than all five personas answering
# every topic identically. Categories are the 4 special ones (today/dasha/
# dosha/yoga) plus every key in _TOPIC_HOUSE; every category is owned by
# exactly one Rishi so a reverse lookup (_CATEGORY_RISHI) is unambiguous.
_RISHI_SPECIALTY: dict[str, set[str]] = {
    "vasishtha": {"education", "travel", "foreign_travel_timing", "relocation_decision"},
    "parashara": {"dasha", "today", "year_ahead", "life_theme"},
    "gargi": {
        "marriage", "family", "friends", "siblings", "children", "marriage_timing", "children_timing",
        "marriage_decision",
    },
    "agastya": {"dosha", "yoga", "health"},
    "bhrigu": {
        "career", "money", "career_timing", "wealth_timing",
        # Phase 2/3/5 sub-intents — same specialist as career/wealth/money,
        # since they're career-, business-, or asset-flavored variants of
        # that same domain, not a new topic of their own.
        "career_promotion_timing", "business_expansion_timing", "business_partnership_timing",
        "job_change_decision", "business_start_decision", "house_purchase_decision",
        "property_sale_intent", "property_inheritance_intent", "property_relocation_intent",
    },
}
_CATEGORY_RISHI: dict[str, str] = {
    category: rishi for rishi, categories in _RISHI_SPECIALTY.items() for category in categories
}


def detect_answering_rishi(message: str, birth_year: int | None = None) -> str | None:
    """Which of the 5 specialists classically 'owns' this message's primary
    topic — used to attribute a reply (e.g. "via Bhrigu — career & money")
    regardless of who's actually chatting. Deliberately independent of
    `rishi_id`/`chat_reply`: this only reflects the QUESTION's topic, not
    who answered it, so it works the same whether a specialist answered
    directly or the generalist "vyasa" persona (see _RISHI_SPECIALTY —
    intentionally left out of it, so it always answers everything itself)
    did. Returns None when no known category matched at all."""
    categories = _detect_categories(message.lower(), birth_year)
    return _CATEGORY_RISHI.get(categories[0]) if categories else None
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

_GREETING_REPLY_SPECIALIST = {
    "en": "Namaste! I'm {name} — I focus on {domain}. What would you like to know?",
    "hi": "नमस्ते! मैं {name} हूं — मैं {domain} पर मार्गदर्शन देता हूं। आप क्या जानना चाहेंगे?",
    "hinglish": "Namaste! Main {name} hoon — main {domain} mein guide karta hoon. Aap kya jaanna chahenge?",
}
_GREETING_REPLY_GENERAL = {
    "en": (
        "Namaste! I'm Vyasa — ask me anything about your career, marriage, money, health, "
        "family, current timing, or today. What's on your mind?"
    ),
    "hi": (
        "नमस्ते! मैं व्यास हूं — करियर, शादी, धन, सेहत, परिवार, मौजूदा समय या आज के बारे में कुछ भी "
        "पूछिए। आपके मन में क्या है?"
    ),
    "hinglish": (
        "Namaste! Main Vyasa hoon — career, shaadi, paisa, health, family, current timing ya aaj "
        "ke baare mein kuch bhi puchiye. Aapke mann mein kya hai?"
    ),
}


def build_greeting_reply(rishi_id: str | None, language: str) -> str:
    """The very first reply in a brand-new conversation when the user's
    opening message is itself just a greeting (see message_is_greeting) —
    a warm hello back, introducing this persona's own specialty when one
    exists, instead of the generic "here's what you can ask me" fallback
    every other unclassifiable message gets."""
    if rishi_id in _RISHI_NAME_EN:
        name = _RISHI_NAME_HI[rishi_id] if language == "hi" else _RISHI_NAME_EN[rishi_id]
        domain = _RISHI_DOMAIN_HI[rishi_id] if language == "hi" else _RISHI_DOMAIN_EN[rishi_id]
        template = _GREETING_REPLY_SPECIALIST.get(language, _GREETING_REPLY_SPECIALIST["en"])
        return template.format(name=name, domain=domain)
    return _GREETING_REPLY_GENERAL.get(language, _GREETING_REPLY_GENERAL["en"])


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
    # Vyasa is deliberately NOT in _RISHI_SPECIALTY (see above) — a
    # generalist who answers every category directly, never redirecting.
    # Still gets a lead-in for personality, unlike the bare persona-agnostic
    # path this app used before any Rishi personas existed.
    "vyasa": [
        "Looking at your real chart:",
        "Here's what your chart actually shows:",
        "Drawing on your full chart:",
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
    "vyasa": [
        "आपकी असली कुंडली देखने पर:",
        "आपकी कुंडली यह दिखाती है:",
        "आपकी पूरी कुंडली के आधार पर:",
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


def _asked_about(message: str, keywords: list[str]) -> bool:
    return _contains_any_keyword(message, keywords)


# career_timing's own keyword list is deliberately broad and includes
# "promotion"/"promoted"/"business" (see _TOPIC_KEYWORDS["career"]) — so a
# message asking specifically about a promotion, business expansion, or a
# business partnership ALSO satisfies the generic career_timing match. The
# Phase 2 sub-intents (career_promotion_timing/business_expansion_timing/
# business_partnership_timing) were built to be checked "alongside, not
# instead of" that generic parent (see the comment above
# _CAREER_PROMOTION_KEYWORDS) on the assumption an LLM would receive both
# windows and pick/merge them intelligently. The deterministic template
# path (chat_reply, used whenever OpenAI is unavailable) has no such
# judgment — it just concatenates every matched category's answer — so
# without this, a plain promotion question came back with the SAME window
# described twice: once framed as "a career or job change" and once as "a
# promotion". Since each sub-intent's own house rule already covers its
# parent's primary house (see life_event_timing.EVENT_HOUSE_WEIGHTS), the
# generic parent adds no real information once the specific one has fired,
# so it's suppressed the same way a "_timing" category already suppresses
# its plain-topic sibling below.
_SUB_INTENT_SUPPRESSES_PARENT = {
    "career_promotion_timing": "career_timing",
    "business_expansion_timing": "career_timing",
    "business_partnership_timing": "career_timing",
}

# A "_timing" category and its plain-topic sibling both key off the same
# underlying topic keywords (message_mentions_marriage_timing REQUIRES the
# "marriage" topic keywords to be present, for instance) — so whenever the
# timing category fires, the topic loop below must not also add its plainer
# sibling, or the reply would answer the same thing twice (once with real
# dasha-window data, once with the static house text).
_TIMING_SUPPRESSES_TOPIC = {
    "marriage_timing": "marriage",
    "career_timing": "career",
    "wealth_timing": "money",
    "children_timing": "children",
    "foreign_travel_timing": "travel",
    # "business" isn't its own _TOPIC_HOUSE topic — it's folded into
    # "career" (see _TOPIC_KEYWORDS["career"]) — so all three Phase 2/3
    # sub-intents suppress that same generic topic.
    "career_promotion_timing": "career",
    "business_expansion_timing": "career",
    "business_partnership_timing": "career",
}
_TIMING_CATEGORIES = frozenset(_TIMING_SUPPRESSES_TOPIC)
# The reverse of the "primary" (non-sub-intent) entries above — used by
# chat.py to automatically also pull real timing windows alongside a plain
# topic answer ("what does my chart say about my career") even when the
# user didn't separately ask "when", so the reply can include a genuine
# future timeline instead of only the static house-based read.
_TOPIC_TIMING_COUNTERPART = {
    "career": "career_timing",
    "money": "wealth_timing",
    "marriage": "marriage_timing",
    "children": "children_timing",
    "travel": "foreign_travel_timing",
}
_MAX_CATEGORIES_PER_REPLY = 2


def _detect_categories(message: str, birth_year: int | None = None) -> list[str]:
    """Returns every real-life category this message plausibly asks about,
    in priority order, capped at _MAX_CATEGORIES_PER_REPLY — a compound
    question ("how's my career and marriage looking?") gets both answered
    for real instead of only whichever topic happened to be checked first.

    "today" stays an exclusive, first-priority match (unchanged from the
    single-category behaviour this replaces) since a "how's today" question
    is rarely genuinely compound with something else."""
    if _asked_about(message, _TODAY_KEYWORDS):
        return ["today"]

    found: list[str] = []

    def add(cat: str) -> None:
        if cat not in found:
            found.append(cat)

    if message_mentions_marriage_timing(message):
        add("marriage_timing")
    if message_mentions_career_timing(message):
        add("career_timing")
    if message_mentions_wealth_timing(message):
        add("wealth_timing")
    if message_mentions_children_timing(message):
        add("children_timing")
    if message_mentions_foreign_travel_timing(message):
        add("foreign_travel_timing")
    if message_mentions_career_promotion_timing(message):
        add("career_promotion_timing")
    if message_mentions_business_expansion_timing(message):
        add("business_expansion_timing")
    if message_mentions_business_partnership_timing(message):
        add("business_partnership_timing")

    for sub_intent, parent in _SUB_INTENT_SUPPRESSES_PARENT.items():
        if sub_intent in found and parent in found:
            found.remove(parent)
    if message_mentions_job_change_decision(message):
        add("job_change_decision")
    if message_mentions_business_start_decision(message):
        add("business_start_decision")
    if message_mentions_relocation_decision(message):
        add("relocation_decision")
    if message_mentions_house_purchase_decision(message):
        add("house_purchase_decision")
    if message_mentions_marriage_decision(message):
        add("marriage_decision")
    if message_mentions_property_sale(message):
        add("property_sale_intent")
    if message_mentions_property_inheritance(message):
        add("property_inheritance_intent")
    if message_mentions_property_relocation(message):
        add("property_relocation_intent")
    if message_mentions_year_ahead(message):
        add("year_ahead")

    # Generic "dasha" only applies when nothing more specific already
    # matched — "when will I get married" already shares its "when"/"kab"
    # timing hint with _DASHA_KEYWORDS and shouldn't also get the generic
    # "you're running X Mahadasha" sentence bolted on.
    if not (_TIMING_CATEGORIES & set(found)) and _asked_about(message, _DASHA_KEYWORDS):
        add("dasha")
    if _asked_about(message, _DOSHA_KEYWORDS):
        add("dosha")
    if _asked_about(message, _YOGA_KEYWORDS):
        add("yoga")

    suppressed_topics = {_TIMING_SUPPRESSES_TOPIC[c] for c in found if c in _TIMING_SUPPRESSES_TOPIC}
    for topic in _TOPIC_HOUSE:
        if topic in suppressed_topics:
            continue
        if _asked_about(message, _TOPIC_KEYWORDS[topic]):
            add(topic)

    # General "what was going on then" reflection — only when nothing more
    # specific already matched (a life-event category with past tense
    # already gets its own real past-direction answer; this is the fallback
    # for a past question that isn't about one specific life area) AND the
    # message actually resolves to a real date (never guessed).
    if not found and birth_year is not None and message_mentions_past_tense(message):
        current_year = datetime.now(timezone.utc).year
        if resolve_past_reference(message, birth_year, current_year) is not None:
            add("life_theme")

    return found[:_MAX_CATEGORIES_PER_REPLY]


def _compute_answer_for_category(
    category: str,
    context: dict[str, Any],
    hi: bool,
    daily: dict[str, Any],
    yogas: list[dict[str, str]],
    mahadasha_lord: str | None,
    antardasha_lord: str | None,
) -> str | None:
    """The exact per-category answer logic chat_reply used to inline as one
    long if/elif chain — pulled out so it can be called once per detected
    category (see _detect_categories) instead of only ever the first one
    that matched."""
    if category == "today":
        parts = [daily.get("rating_reason"), daily.get("brutal_truth")]
        if daily.get("festival"):
            parts.append(f"आज {daily['festival']} है।" if hi else f"Today is {daily['festival']}.")
        return " ".join(p for p in parts if p) or None

    if category == "marriage_timing":
        windows: list[dict[str, Any]] = context.get("marriage_timing_windows") or []
        direction = context.get("marriage_timing_direction", "future")
        label = "विवाह या किसी गंभीर साझेदारी" if hi else "marriage or a serious partnership"
        reply = _format_timing_reply(windows, label, direction, context.get("birth_year"), hi)
        pattern_sentence = _personal_pattern_sentence(category, context, hi)
        return f"{reply}\n\n{pattern_sentence}" if pattern_sentence else reply

    if category in _LIFE_EVENT_CONTEXT_KEY:
        return _life_event_chat_answer(category, context, hi)

    if category in (
        "job_change_decision", "business_start_decision", "house_purchase_decision", "marriage_decision",
        "property_sale_intent", "property_inheritance_intent", "property_relocation_intent",
    ):
        # A verdict + reasoning (see prediction_service.get_decision /
        # get_marriage_decision / get_property_analysis), not a
        # ranked window list — the composed `reasoning` text already reads
        # as a complete answer on its own, same as how the timing categories
        # above hand back _format_timing_reply's finished sentence rather
        # than raw window data for chat_reply to re-narrate.
        decision: dict[str, Any] | None = context.get(category)
        if not decision:
            return None
        reply = decision.get("note") or decision.get("reasoning")
        if not reply:
            return None
        pattern_sentence = _personal_pattern_sentence(category, context, hi)
        return f"{reply}\n\n{pattern_sentence}" if pattern_sentence else reply

    if category == "life_theme":
        theme_data: dict[str, Any] | None = context.get("life_theme")
        return theme_data.get("theme") if theme_data else None

    if category == "year_ahead":
        year_ahead: dict[str, Any] | None = context.get("year_ahead")
        if not year_ahead:
            return None
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
        return answer

    if category == "dasha":
        if not (mahadasha_lord and antardasha_lord):
            return None
        lead = (
            f"फिलहाल आपकी {mahadasha_lord} महादशा चल रही है, जिसके भीतर {antardasha_lord} की अंतर्दशा चल रही "
            "है — यही संयोजन इस समय आपके अनुभवों की मुख्य दिशा तय कर रहा है।"
            if hi
            else f"You're currently running your {mahadasha_lord} Mahadasha, with {antardasha_lord} Antardasha "
            "inside it — that combination is what's actually shaping this stretch of your life."
        )
        # The mechanism sentence above only names WHICH planets are running —
        # it doesn't say what that actually means day-to-day. Append the same
        # real, plain-language effect one-liner already used by period
        # analysis and life-theme reflection (_PERIOD_CONTENT), keyed by the
        # antardasha lord's actual planet code (not its display name, which
        # is what mahadasha_lord/antardasha_lord hold) — caught live: a user
        # asking "what dasha am I in" got the mechanism but no effect.
        antardasha_code: str | None = context.get("antardasha_lord_code")
        if antardasha_code:
            content_pool = _PERIOD_CONTENT_HI if hi else _PERIOD_CONTENT_EN
            effect = content_pool.get(antardasha_code, content_pool["Mo"])["one_liner"]
            return f"{lead} {effect}"
        return lead

    if category == "dosha":
        # Two real, computed dosha-like signals — a static one (yogas, from
        # the natal chart alone: Manglik/Kaal Sarp/Kemadruma) and a
        # time-aware one (daily_reading's doshas list, which also carries
        # Sade Sati and Dhaiya — both depend on WHERE Saturn is transiting
        # right now, not just the natal chart). Before this, "do I have any
        # dosha" only ever checked the first list, so a real, currently
        # active Sade Sati or Dhaiya was silently omitted — caught live: the
        # same chart's Dhaiya only ever surfaced through a life-theme
        # question, never a direct dosha question.
        # A direct "yes/no" answer first — the previous version returned only
        # the classical rule text (which houses are checked, etc.) and never
        # actually said whether the person IS Manglik, caught live from a
        # real "Am I Manglik?" question. chat_summary is written as a
        # standalone yes-statement per finding; see
        # chart_explanation_service._MAHAPURUSHA_CHAT_SUMMARY_EN etc.
        findings = [y for y in yogas if y["key"] in _DOSHA_KEYS]
        sentences = [y["chat_summary"] for y in findings]

        daily_doshas = {d["key"]: d for d in (daily.get("doshas") or [])}
        if daily_doshas.get("sade_sati", {}).get("is_present"):
            sentences.append(
                "हां, शनि की साढ़े साती फिलहाल आपके लिए सक्रिय है — यह शास्त्रीय रूप से सामान्य से ज़्यादा मेहनत और "
                "संघर्ष वाला दौर माना जाता है।"
                if hi else
                "Yes, Saturn's Sade Sati is currently active for you — classically a heavier, more effortful "
                "period than usual."
            )
        if daily_doshas.get("dhaiya", {}).get("is_present"):
            sentences.append(
                "हां, शनि की ढैया फिलहाल आपके लिए सक्रिय है — यह भी एक जाना-पहचाना कठिन दौर माना जाता है, हालांकि "
                "आमतौर पर साढ़े साती से हल्का।"
                if hi else
                "Yes, Saturn's Dhaiya is currently active for you — another classically difficult stretch, "
                "usually lighter than Sade Sati."
            )

        if sentences:
            return " ".join(sentences)
        return (
            "नहीं — आपकी कुंडली में मंगलिक, कालसर्प, केमद्रुम, साढ़े साती या ढैया जैसा कोई प्रमुख दोष अभी सक्रिय नहीं मिला।"
            if hi
            else "No — I didn't find Manglik, Kaal Sarp, Kemadruma, Sade Sati, or Dhaiya active in your chart "
            "right now."
        )

    if category == "yoga":
        findings = [y for y in yogas if y["key"] not in _DOSHA_KEYS]
        if findings:
            return " ".join(y["chat_summary"] for y in findings)
        return (
            "नहीं — आपकी कुंडली में कोई विशेष शास्त्रीय योग नहीं मिला। यह कमज़ोर कुंडली का संकेत नहीं है, कई मज़बूत "
            "कुंडलियों में भी कोई नामी योग नहीं होता।"
            if hi
            else "No — I didn't detect a named classical yoga in your chart. That's not a sign of a weak "
            "chart — plenty of strong charts don't carry one either."
        )

    if category in _TOPIC_HOUSE:
        # A plain good/bad/mixed verdict, not the detailed planet-by-planet
        # explanation (house_breakdown above) — chat answers a "what does my
        # chart say about X" question with a direct, jargon-free statement
        # about that life area, not a chart-reading lesson. See
        # chart_explanation_service._VERDICT_BY_HOUSE_EN/HI.
        house_verdict: dict[int, str] = context.get("house_verdict", {})
        return house_verdict.get(_TOPIC_HOUSE[category])

    return None


_MULTI_TOPIC_CONNECTOR_EN = " Also, "
_MULTI_TOPIC_CONNECTOR_HI = " वहीं, "


def _join_multi_topic_answers(answers: list[str], hi: bool) -> str:
    if len(answers) == 1:
        return answers[0]
    connector = _MULTI_TOPIC_CONNECTOR_HI if hi else _MULTI_TOPIC_CONNECTOR_EN
    return connector.join(answers)


def _rishi_pointer_multi(hi: bool, categories: list[str], history: list[dict[str, str]]) -> str:
    """Same idea as _rishi_pointer, generalized to a compound question where
    more than one of the detected categories falls outside the asking
    Rishi's specialty — points to every distinct owner once, not once per
    category (asking Bhrigu about both career timing and children timing
    should name Gargi once, not repeat her)."""
    if len(categories) == 1:
        return _rishi_pointer(hi, categories[0], history)
    owners: list[str] = []
    for c in categories:
        owner_id = _CATEGORY_RISHI[c]
        name = _RISHI_NAME_HI[owner_id] if hi else _RISHI_NAME_EN[owner_id]
        if name not in owners:
            owners.append(name)
    if len(owners) == 1:
        return _rishi_pointer(hi, categories[0], history)
    owners_str = (" या ").join(owners) if hi else " or ".join(owners)
    return (
        f"इस पर और जानने के लिए {owners_str} से बात करें।"
        if hi
        else f"For more detail on this, chat with {owners_str}."
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
        yogas: list[dict[str, str]] = context.get("yogas", [])
        daily: dict[str, Any] = context.get("daily_reading", {})
        mahadasha_lord = context.get("mahadasha_lord")
        antardasha_lord = context.get("antardasha_lord")
        rishi_id = context.get("rishi_id")
        birth_year = context.get("birth_year")

        message = history[-1]["content"].lower() if history else ""
        # chat.py always sets context["detected_categories"] (it's what
        # openai_interpreter already reads — see its own use of the same
        # key) — prefer that over re-deriving from the raw message text
        # whenever it's present, since chat.py's own list can carry a
        # category that isn't recoverable from the latest message alone
        # (e.g. a bare "yes" answering a life-state gate question — see
        # chat.py's career-employment gate handling, which injects
        # career_promotion_timing after a plain "yes" that _detect_
        # categories itself would never match on its own). Re-derive only
        # when the caller genuinely didn't supply one (e.g. calling this
        # directly in tests without going through chat.py).
        context_categories = context.get("detected_categories")
        categories = context_categories if context_categories is not None else _detect_categories(message, birth_year)

        def _out_of_scope(cat: str) -> bool:
            return rishi_id in _RISHI_SPECIALTY and cat not in _RISHI_SPECIALTY[rishi_id]

        # A real answer is attempted for EVERY detected category regardless
        # of specialty — Bhrigu still answers a marriage question for real,
        # he just also points to Gargi afterward. Only when NO category
        # produced any real answer at all does an out-of-specialty category
        # fall back to a pure redirect (see below) instead of a real fact.
        answered: list[tuple[str, str]] = [
            (c, a)
            for c in categories
            if (a := _compute_answer_for_category(c, context, hi, daily, yogas, mahadasha_lord, antardasha_lord))
        ]

        if answered:
            combined = _join_multi_topic_answers([a for _, a in answered], hi)
            # In-character lead-in before the real fact — a rotating choice
            # per Rishi (see _pick_variant) so the same question asked twice
            # doesn't come back as the identical line every time. Only
            # applied when a rishi_id is known; the persona-agnostic caller
            # (no rishi_id) gets the bare answer, unchanged.
            if rishi_id in _RISHI_LEAD_IN_EN:
                lead_in = _pick_variant(_RISHI_LEAD_IN_HI[rishi_id] if hi else _RISHI_LEAD_IN_EN[rishi_id], history)
                combined = f"{lead_in} {combined}"
            out_of_scope_answered = [c for c, _ in answered if _out_of_scope(c)]
            if out_of_scope_answered:
                combined = f"{combined} {_rishi_pointer_multi(hi, out_of_scope_answered, history)}"
            return combined

        out_of_scope_detected = [c for c in categories if _out_of_scope(c)]
        if out_of_scope_detected:
            # No real data exists for any detected category at all (e.g. no
            # current dasha on file) — nothing to answer with, so this is
            # the one case that's a pure redirect. Uses whichever
            # out-of-scope category was detected first, same as the
            # single-category behaviour this replaces.
            return _rishi_refusal(hi, rishi_id, out_of_scope_detected[0])

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
