"""Turns a computed chart into the kind of house-by-house, "what's affecting
what" explanation a real astrologer would give — the piece this app was
missing: real placements were being calculated all along, but nothing
explained what they actually mean in plain language.

Two things, both deterministic (no LLM):
  1. `build_house_breakdown` — for every one of the 12 houses, which
     planet(s) sit there, how well-placed each one is (dignity), and what
     that combination means for the life area that house governs. An empty
     house still gets a real, non-generic line about how it plays out
     through its lord instead.
  2. `detect_yogas` — real yoga/dosha detection (Gajakesari, the five Panch
     Mahapurusha yogas, one conservative Raj Yoga pattern, Manglik, Kaal
     Sarp, Kemadruma) using the astro modules already built this project but
     never actually surfaced in any response until now.

Both languages are computed together (same convention as the rest of
chart_service — one cached row serves either language), reusing the same
phrase-generation toolkit (house significations, planet tone, dignity
qualifiers) already shared across daily_reading_service and
focus_reading_service.
"""
from app.astro.charts import ChartResult, house_number
from app.astro.constants import PLANET_NAMES_EN, PLANET_NAMES_HI, SIGN_NAMES_EN, SIGN_NAMES_HI, PlanetKey
from app.astro.doshas import CLASSICAL_PLANETS, compute_kaal_sarp_dosha, compute_kemadruma_dosha
from app.astro.manglik import compute_manglik_facts
from app.astro.natal_insights import house_lord, planet_dignity
from app.astro.yogas import (
    MAHAPURUSHA_PLANET_NAMES_HI,
    compute_panch_mahapurusha_yogas,
    has_conservative_raj_yoga,
    has_gajakesari_yoga,
)
from app.services.interpretation.templates import (
    _DIGNITY_QUALIFIER_EN,
    _DIGNITY_QUALIFIER_HI,
    _FOCUS_BY_HOUSE_EN,
    _FOCUS_BY_HOUSE_HI,
    _LIFE_FRAMING_EN,
    _LIFE_FRAMING_HI,
    _TONE_BY_LORD_EN,
    _TONE_BY_LORD_HI,
    _a_or_an,
    _hindi_house,
    _ordinal,
    _strip_trailing_stop,
)

# A one-line, jargon-free verdict per house — no planet names, no dignity
# terms, just a plain "is this good, bad, or mixed for this area of your
# life" statement (favorable/unfavorable/mixed), for chat's "what does my
# chart say about X" answers. The detailed planet-by-planet explanation
# above stays available separately for the dedicated chart-explanation
# screen, which is a different reading context from a quick chat answer.
_VERDICT_BY_HOUSE_EN: dict[int, dict[str, str]] = {
    1: {
        "favorable": "This is a good time to focus on yourself and build confidence.",
        "unfavorable": "You may feel low on energy or unsure of yourself at times.",
        "mixed": "Your confidence and energy may go up and down.",
    },
    2: {
        "favorable": "This is good for your money — financial gains are likely.",
        "unfavorable": "You may face money troubles or financial loss.",
        "mixed": "You may see both gains and losses with money.",
    },
    3: {
        "favorable": "This is a good time for communication — your words will land well.",
        "unfavorable": "Communication may lead to misunderstandings.",
        "mixed": "Communication may go smoothly at times and cause friction at other times.",
    },
    4: {
        "favorable": "This is good for your home and family life.",
        "unfavorable": "There may be some tension or difficulty at home or with family.",
        "mixed": "Home and family life may have both easy and difficult times.",
    },
    5: {
        "favorable": "This is a good time for romance and creative pursuits.",
        "unfavorable": "Romance or creative plans may face difficulty.",
        "mixed": "Romance and creativity may bring mixed results.",
    },
    6: {
        "favorable": "This is good for your health and daily routine.",
        "unfavorable": "You may need to be careful about your health.",
        "mixed": "Your health may be fine at times and weak at other times.",
    },
    7: {
        "favorable": "This is a good sign for your relationships and partnerships.",
        "unfavorable": "This can affect your relationships — expect some difficulty or delay.",
        "mixed": "Your relationships may have both good and hard moments.",
    },
    8: {
        "favorable": "Sudden changes are likely to work in your favor.",
        "unfavorable": "Be careful of sudden setbacks or unexpected trouble.",
        "mixed": "Unexpected changes may bring both good and bad surprises.",
    },
    9: {
        "favorable": "This is good for learning, higher studies, and travel.",
        "unfavorable": "Learning or travel plans may face obstacles.",
        "mixed": "Learning and travel may go smoothly at times and hit snags at other times.",
    },
    10: {
        "favorable": "This is a good time for your career.",
        "unfavorable": "Your career may see struggle or slow progress.",
        "mixed": "Your career may have both good phases and hard phases.",
    },
    11: {
        "favorable": "This is good for gains, income, and friendships.",
        "unfavorable": "You may see fewer gains than expected, or friction with friends.",
        "mixed": "Gains and friendships may go up and down.",
    },
    12: {
        "favorable": "This is a good time for rest, healing, or spiritual growth.",
        "unfavorable": "You may feel drained or face unnecessary expenses.",
        "mixed": "Rest and letting go may feel easy at times and hard at other times.",
    },
}
_VERDICT_BY_HOUSE_HI: dict[int, dict[str, str]] = {
    1: {
        "favorable": "यह समय खुद पर ध्यान देने और आत्मविश्वास बढ़ाने के लिए अच्छा है।",
        "unfavorable": "आप कभी-कभी ऊर्जा की कमी या आत्मविश्वास में कमी महसूस कर सकते हैं।",
        "mixed": "आपका आत्मविश्वास और ऊर्जा ऊपर-नीचे हो सकती है।",
    },
    2: {
        "favorable": "यह आपके धन के लिए अच्छा है — आर्थिक लाभ की संभावना है।",
        "unfavorable": "आपको पैसों से जुड़ी परेशानी या नुकसान हो सकता है।",
        "mixed": "धन के मामले में लाभ और नुकसान दोनों हो सकते हैं।",
    },
    3: {
        "favorable": "यह संवाद के लिए अच्छा समय है — आपकी बातों का असर पड़ेगा।",
        "unfavorable": "संवाद में गलतफहमी हो सकती है।",
        "mixed": "संवाद कभी अच्छा रहेगा तो कभी तनावपूर्ण।",
    },
    4: {
        "favorable": "यह घर और परिवार के लिए अच्छा समय है।",
        "unfavorable": "घर या परिवार में कुछ तनाव या परेशानी हो सकती है।",
        "mixed": "पारिवारिक जीवन में अच्छे और मुश्किल दोनों समय आ सकते हैं।",
    },
    5: {
        "favorable": "यह प्रेम और रचनात्मक कामों के लिए अच्छा समय है।",
        "unfavorable": "प्रेम या रचनात्मक योजनाओं में परेशानी आ सकती है।",
        "mixed": "प्रेम और रचनात्मकता में मिले-जुले नतीजे मिल सकते हैं।",
    },
    6: {
        "favorable": "यह आपके स्वास्थ्य और दिनचर्या के लिए अच्छा है।",
        "unfavorable": "आपको अपने स्वास्थ्य का ध्यान रखने की ज़रूरत है।",
        "mixed": "स्वास्थ्य कभी ठीक रहेगा तो कभी कमज़ोर।",
    },
    7: {
        "favorable": "यह आपके रिश्तों के लिए अच्छा संकेत है।",
        "unfavorable": "इससे आपके रिश्तों पर असर पड़ सकता है और कुछ मुश्किलें आ सकती हैं।",
        "mixed": "आपके रिश्तों में अच्छे और मुश्किल दोनों पल आ सकते हैं।",
    },
    8: {
        "favorable": "अचानक होने वाले बदलाव आपके पक्ष में जा सकते हैं।",
        "unfavorable": "अचानक होने वाली परेशानियों से सावधान रहें।",
        "mixed": "अचानक बदलाव अच्छे और बुरे दोनों तरह के हो सकते हैं।",
    },
    9: {
        "favorable": "यह पढ़ाई, उच्च शिक्षा और यात्रा के लिए अच्छा समय है।",
        "unfavorable": "पढ़ाई या यात्रा की योजनाओं में रुकावट आ सकती है।",
        "mixed": "पढ़ाई और यात्रा में कभी आसानी तो कभी रुकावट आ सकती है।",
    },
    10: {
        "favorable": "यह आपके करियर के लिए अच्छा समय है।",
        "unfavorable": "आपके करियर में संघर्ष या धीमी प्रगति हो सकती है।",
        "mixed": "करियर में अच्छे और मुश्किल दोनों दौर आ सकते हैं।",
    },
    11: {
        "favorable": "यह लाभ, आमदनी और दोस्ती के लिए अच्छा है।",
        "unfavorable": "उम्मीद से कम लाभ हो सकता है या दोस्तों से थोड़ी अनबन हो सकती है।",
        "mixed": "लाभ और दोस्ती के मामले में उतार-चढ़ाव रह सकता है।",
    },
    12: {
        "favorable": "यह आराम, उपचार या आध्यात्मिक विकास के लिए अच्छा समय है।",
        "unfavorable": "आप थका हुआ महसूस कर सकते हैं या अनावश्यक खर्च हो सकता है।",
        "mixed": "आराम और चीज़ों को छोड़ने का यह अनुभव कभी आसान तो कभी मुश्किल हो सकता है।",
    },
}

# A one-line plain-language "why" that follows the verdict above — same
# reason text regardless of which house/topic, since the underlying cause is
# always the same shape (strong support / real strain / no strong pull
# either way). Deliberately still no planet names or astrology terms, so the
# verdict doesn't read as an unexplained, arbitrary label.
_VERDICT_REASON_EN: dict[str, str] = {
    "favorable": "There's a strong, positive push behind this right now, so things are likely to work in your favor.",
    "unfavorable": "There's real strain behind this right now, so expect some extra effort or difficulty.",
    "mixed": "There's no strong push in either direction right now, so a lot depends on your own effort and choices.",
}
_VERDICT_REASON_HI: dict[str, str] = {
    "favorable": "अभी इसके पीछे एक मज़बूत, सकारात्मक ताकत है, इसलिए चीज़ें आपके पक्ष में जाने की संभावना है।",
    "unfavorable": "अभी इसके पीछे वास्तविक दबाव है, इसलिए थोड़ी ज़्यादा मेहनत या मुश्किल की उम्मीद रखें।",
    "mixed": "अभी इसके पीछे कोई मज़बूत ताकत नहीं है, इसलिए काफ़ी कुछ आपकी अपनी मेहनत और चुनाव पर निर्भर करता है।",
}


def _dignity_bucket(dignities: list[str | None]) -> str:
    """Collapses one or more planets' classical dignity into a single plain
    verdict bucket. Rahu/Ketu (dignity always None) simply don't vote either
    way. Conflicting signals (one planet strong, another weak) and "nothing
    strong either way" both land on "mixed" deliberately — a real, honest
    answer rather than picking an arbitrary winner."""
    good = any(d in ("exalted", "own_sign") for d in dignities)
    bad = any(d == "debilitated" for d in dignities)
    if good and bad:
        return "mixed"
    if good:
        return "favorable"
    if bad:
        return "unfavorable"
    return "mixed"


# Natal-placement framing for a *neutral*-dignity planet (or Rahu/Ketu, which
# have no classical dignity) — deliberately NOT reusing _PERIOD_CONTENT's
# one-liners here, since those are written for "this is currently your
# running dasha period" (time-bound) and would misleadingly imply a natal
# placement fact is temporary. This says WHERE this planet's effect
# concretely shows up in the person's life, as a permanent chart fact.
_NEUTRAL_EFFECT_EN: dict[PlanetKey, str] = {
    "Su": "This is where you naturally look for recognition and validation.",
    "Mo": "This is where your moods and emotional needs show up most.",
    "Ma": "This is where you act fast and can be impatient.",
    "Me": "This is where your mind stays busiest and most active.",
    "Ju": "This is where you naturally look for growth and expansion.",
    "Ve": "This is where you seek comfort, beauty, and connection.",
    "Sa": "This is where you move slowly but build something lasting.",
    "Ra": "This is where restless, unconventional energy tends to show up.",
    "Ke": "This is where you may feel detached or want to let go.",
}
_NEUTRAL_EFFECT_HI: dict[PlanetKey, str] = {
    "Su": "यहां आप आमतौर पर पहचान और सराहना की तलाश करते हैं।",
    "Mo": "यहां आपके मूड और भावनात्मक ज़रूरतें सबसे ज़्यादा दिखती हैं।",
    "Ma": "यहां आप तेज़ी से काम करते हैं और अधीर हो सकते हैं।",
    "Me": "यहां आपका मन सबसे ज़्यादा सक्रिय और व्यस्त रहता है।",
    "Ju": "यहां आप स्वाभाविक रूप से विकास और विस्तार की तलाश करते हैं।",
    "Ve": "यहां आप सुख, सुंदरता और जुड़ाव की तलाश करते हैं।",
    "Sa": "यहां आप धीरे चलते हैं पर कुछ टिकाऊ बनाते हैं।",
    "Ra": "यहां बेचैन, अपरंपरागत ऊर्जा दिखने की संभावना रहती है।",
    "Ke": "यहां आप अलगाव महसूस कर सकते हैं या छोड़ना चाहते हैं।",
}

# A short, practical closing line per planet — what to actually DO with the
# tendency described above, explicitly tied back to whichever house/life-area
# it's being read for (see build_house_breakdown). This is the piece that
# turns "here's a fact about your chart" into a real, useful explanation
# instead of a flat statement.
_PRACTICAL_TIP_EN: dict[PlanetKey, str] = {
    "Su": "it helps to let your effort be seen instead of staying in the background",
    "Mo": "it helps to notice how you're feeling here instead of pushing it aside",
    "Ma": "it helps to slow down and think before acting on impulse",
    "Me": "it helps to say what's actually on your mind instead of overthinking it",
    "Ju": "it helps to trust your instinct to grow here, even if it feels like a stretch",
    "Ve": "it helps to make real time for comfort and connection here",
    "Sa": "it helps to be patient — progress here is slow but tends to last",
    "Ra": "it helps to stay grounded here instead of chasing every new impulse",
    "Ke": "it helps to stay engaged here instead of withdrawing when it gets hard",
}
_PRACTICAL_TIP_HI: dict[PlanetKey, str] = {
    "Su": "यहां पीछे रहने के बजाय अपने काम को सामने लाना फायदेमंद रहेगा",
    "Mo": "यहां अपनी भावनाओं को नज़रअंदाज़ करने के बजाय उन्हें पहचानना फायदेमंद रहेगा",
    "Ma": "यहां जल्दबाज़ी में कुछ करने से पहले थोड़ा रुककर सोचना फायदेमंद रहेगा",
    "Me": "यहां ज़्यादा सोचने के बजाय मन की बात कहना फायदेमंद रहेगा",
    "Ju": "यहां बढ़ने की अपनी सहज इच्छा पर भरोसा करना फायदेमंद रहेगा, भले ही यह मुश्किल लगे",
    "Ve": "यहां सुख और जुड़ाव के लिए असली समय निकालना फायदेमंद रहेगा",
    "Sa": "यहां धैर्य रखना फायदेमंद रहेगा — प्रगति धीमी है पर टिकाऊ होती है",
    "Ra": "यहां हर नई इच्छा के पीछे भागने के बजाय स्थिर रहना फायदेमंद रहेगा",
    "Ke": "यहां मुश्किल होने पर पीछे हटने के बजाय जुड़े रहना फायदेमंद रहेगा",
}

_MAHAPURUSHA_DESCRIPTIONS_EN = {
    "Ma": "Mars is exalted or in its own sign in an angular (Kendra) house — classical Ruchaka Yoga, giving real courage, physical drive, and a natural instinct to lead rather than follow.",
    "Me": "Mercury is exalted or in its own sign in an angular (Kendra) house — classical Bhadra Yoga, giving sharp, quick intellect and real skill in communication.",
    "Ju": "Jupiter is exalted or in its own sign in an angular (Kendra) house — classical Hamsa Yoga, giving wisdom, ethics, and a presence people naturally respect.",
    "Ve": "Venus is exalted or in its own sign in an angular (Kendra) house — classical Malavya Yoga, giving charm, aesthetic sense, and a life with real comfort in it.",
    "Sa": "Saturn is exalted or in its own sign in an angular (Kendra) house — classical Sasa Yoga, giving discipline, authority, and the staying power to outlast hard periods.",
}
_MAHAPURUSHA_DESCRIPTIONS_HI = {
    "Ma": "मंगल किसी केंद्र भाव में उच्च या अपनी राशि में है — शास्त्रीय रुचक योग, जो वास्तविक साहस, शारीरिक ऊर्जा और नेतृत्व की स्वाभाविक प्रवृत्ति देता है।",
    "Me": "बुध किसी केंद्र भाव में उच्च या अपनी राशि में है — शास्त्रीय भद्र योग, जो तेज़ बुद्धि और संवाद कौशल देता है।",
    "Ju": "गुरु किसी केंद्र भाव में उच्च या अपनी राशि में है — शास्त्रीय हंस योग, जो ज्ञान, नैतिकता और सम्मानजनक व्यक्तित्व देता है।",
    "Ve": "शुक्र किसी केंद्र भाव में उच्च या अपनी राशि में है — शास्त्रीय मालव्य योग, जो आकर्षण, सौंदर्यबोध और वास्तविक सुख-सुविधा देता है।",
    "Sa": "शनि किसी केंद्र भाव में उच्च या अपनी राशि में है — शास्त्रीय शश योग, जो अनुशासन, अधिकार और कठिन समय में टिके रहने की क्षमता देता है।",
}

# Direct "yes, you have this" versions of the above, for chat answers — the
# detailed descriptions stay available for the dedicated chart-explanation
# screen (see the verdict_en/hi split on HouseBreakdown for the same pattern).
_MAHAPURUSHA_CHAT_SUMMARY_EN = {
    "Ma": "Yes, you have Ruchaka Yoga — a sign of real courage and natural leadership.",
    "Me": "Yes, you have Bhadra Yoga — a sign of sharp intellect and strong communication skills.",
    "Ju": "Yes, you have Hamsa Yoga — a sign of wisdom and a presence people naturally respect.",
    "Ve": "Yes, you have Malavya Yoga — a sign of charm and a life with real comfort in it.",
    "Sa": "Yes, you have Sasa Yoga — a sign of discipline and the ability to outlast hard times.",
}
_MAHAPURUSHA_CHAT_SUMMARY_HI = {
    "Ma": "हां, आपकी कुंडली में रुचक योग है — यह वास्तविक साहस और स्वाभाविक नेतृत्व क्षमता का संकेत है।",
    "Me": "हां, आपकी कुंडली में भद्र योग है — यह तेज़ बुद्धि और अच्छे संवाद कौशल का संकेत है।",
    "Ju": "हां, आपकी कुंडली में हंस योग है — यह ज्ञान और सम्मानजनक व्यक्तित्व का संकेत है।",
    "Ve": "हां, आपकी कुंडली में मालव्य योग है — यह आकर्षण और वास्तविक सुख-सुविधा भरे जीवन का संकेत है।",
    "Sa": "हां, आपकी कुंडली में शश योग है — यह अनुशासन और कठिन समय में टिके रहने की क्षमता का संकेत है।",
}


def _join_and(names: list[str]) -> str:
    """["Sun", "Mercury"] -> "Sun and Mercury"; ["Sun", "Mercury", "Mars"] -> "Sun, Mercury and Mars"."""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _planet_effect(planet: PlanetKey, dignity: str | None) -> tuple[str, str]:
    """The real, concrete consequence of this planet's placement — not
    another restatement of its dignity/tone, but what that dignity actually
    does for the person: a genuine strength, a genuine challenge, or (for
    Rahu/Ketu, which have no classical dignity, and neutral placements) its
    general character. Reuses the same hand-written per-planet toolkit
    already shared with daily_reading_service/focus_reading_service rather
    than inventing new copy."""
    if dignity == "exalted" or dignity == "own_sign":
        return (
            f"{_strip_trailing_stop(_LIFE_FRAMING_EN[planet]['core_strength'])} — a real strength here.",
            f"यहां {_strip_trailing_stop(_LIFE_FRAMING_HI[planet]['core_strength'])} — यह एक वास्तविक ताकत है।",
        )
    if dignity == "debilitated":
        return (
            f"{_strip_trailing_stop(_LIFE_FRAMING_EN[planet]['core_challenge'])} — a real challenge here.",
            f"यहां {_strip_trailing_stop(_LIFE_FRAMING_HI[planet]['core_challenge'])} — यह एक वास्तविक चुनौती है।",
        )
    return (_NEUTRAL_EFFECT_EN[planet], _NEUTRAL_EFFECT_HI[planet])


def build_planet_theme_sentences(chart: ChartResult) -> dict[PlanetKey, dict]:
    """The classical "significations blend" for a planet: whichever house(s)
    it rules lend their life-area flavor to whichever house it's actually
    placed in — e.g. a 10th lord (career) sitting in the 4th house (home)
    means career satisfaction is often tied to environment/stability, not
    just title or money. This is what makes a sentence about a specific
    planet (a topic's house-lord, or a dasha lord) read as being about THIS
    chart instead of reciting the planet's generic tone — which two houses
    get blended is different for every birth chart, which is the actual
    source of feeling "known" rather than generic.

    Returns both a ready-made prose sentence (theme_en/hi) AND the raw
    numbers/sign names behind it (ruled_houses/placed_house/placed_sign) —
    direct feedback found that naming the actual house numbers and sign
    names (e.g. "your 10th house is Taurus, ruled by Venus, sitting in your
    4th house, Scorpio") read as more genuinely personal than the paraphrased
    prose alone, so the prompt that consumes this can choose to state them
    explicitly rather than only the softened version.

    Used two ways: per-house in build_house_breakdown below (that house's
    own lord), and directly by chat's Mahadasha/Antardasha lord facts (a
    dasha lord isn't necessarily any topic's house-lord, so it needs its own
    lookup by planet code rather than by house)."""
    themes: dict[PlanetKey, dict] = {}
    for planet, placed_house in chart.planet_house.items():
        ruled_houses = [h for h in range(1, 13) if house_lord(h, chart.lagna_sign_index) == planet]
        placed_sign_idx = (chart.lagna_sign_index + placed_house - 1) % 12
        placed_sign_en, placed_sign_hi = SIGN_NAMES_EN[placed_sign_idx], SIGN_NAMES_HI[placed_sign_idx]
        placed_focus_en, placed_focus_hi = _FOCUS_BY_HOUSE_EN[placed_house], _FOCUS_BY_HOUSE_HI[placed_house]
        name_en, name_hi = PLANET_NAMES_EN[planet], PLANET_NAMES_HI[planet]
        if ruled_houses:
            ruled_focus_en = " and ".join(_FOCUS_BY_HOUSE_EN[h] for h in ruled_houses)
            ruled_focus_hi = " और ".join(_FOCUS_BY_HOUSE_HI[h] for h in ruled_houses)
            theme_en = (
                f"{name_en} rules {ruled_focus_en} in your chart, and sits in the house of "
                f"{placed_focus_en} — so that side of life tends to play out through "
                f"{placed_focus_en}, not on its own."
            )
            theme_hi = (
                f"{name_hi} आपकी कुंडली में {ruled_focus_hi} का स्वामी है, और {placed_focus_hi} के भाव में "
                f"बैठा है — इसलिए यह क्षेत्र अक्सर {placed_focus_hi} के ज़रिए ही सामने आता है।"
            )
        else:
            # Rahu/Ketu own no sign, so they never classically "rule" a house
            # — placement alone (via its general tone) still carries meaning.
            tone_en, tone_hi = _TONE_BY_LORD_EN[planet], _TONE_BY_LORD_HI[planet]
            theme_en = f"{name_en} sits in the house of {placed_focus_en}, bringing a {tone_en} quality to that part of life."
            theme_hi = f"{name_hi} {placed_focus_hi} के भाव में बैठा है, जिससे उसमें {tone_hi} जैसा भाव जुड़ता है।"
        themes[planet] = {
            "name_en": name_en,
            "name_hi": name_hi,
            "ruled_houses": ruled_houses,
            "placed_house": placed_house,
            "placed_sign_en": placed_sign_en,
            "placed_sign_hi": placed_sign_hi,
            "theme_en": theme_en,
            "theme_hi": theme_hi,
        }
    return themes


def build_house_breakdown(chart: ChartResult) -> list[dict]:
    names_en, names_hi = PLANET_NAMES_EN, PLANET_NAMES_HI
    focus_en, focus_hi = _FOCUS_BY_HOUSE_EN, _FOCUS_BY_HOUSE_HI
    qualifier_en, qualifier_hi = _DIGNITY_QUALIFIER_EN, _DIGNITY_QUALIFIER_HI
    planet_themes = build_planet_theme_sentences(chart)

    planets_by_house: dict[int, list[PlanetKey]] = {h: [] for h in range(1, 13)}
    for planet, house in chart.planet_house.items():
        planets_by_house[house].append(planet)

    breakdown = []
    for house in range(1, 13):
        sign_idx = (chart.lagna_sign_index + house - 1) % 12
        planets_here = planets_by_house[house]

        if not planets_here:
            lord = house_lord(house, chart.lagna_sign_index)
            lord_house = chart.planet_house[lord]
            lord_dignity = planet_dignity(lord, chart.planet_sign_index[lord])
            verdict_bucket = _dignity_bucket([lord_dignity])
            effect_en, effect_hi = _planet_effect(lord, lord_dignity)
            explanation_en = (
                f"No planet sits directly in this house. How {focus_en[house]} plays out for you depends on "
                f"{names_en[lord]}, this house's ruling planet, who sits in your {_ordinal(lord_house)} house "
                f"and is {qualifier_en[lord_dignity]}. {names_en[lord]} generally brings "
                f"{_a_or_an(_TONE_BY_LORD_EN[lord])} {_TONE_BY_LORD_EN[lord]} quality. {effect_en} "
                f"In {focus_en[house]} specifically, {_PRACTICAL_TIP_EN[lord]}."
            )
            explanation_hi = (
                f"इस भाव में सीधे कोई ग्रह नहीं है। {focus_hi[house]} का अनुभव मुख्यतः इस भाव के स्वामी "
                f"{names_hi[lord]} की स्थिति से तय होगा, जो आपके {_hindi_house(lord_house)} में है और "
                f"{qualifier_hi[lord_dignity]}। {names_hi[lord]} आमतौर पर {_TONE_BY_LORD_HI[lord]} भाव लाता है। "
                f"{effect_hi} खासकर {focus_hi[house]} के मामले में, {_PRACTICAL_TIP_HI[lord]}।"
            )
        elif len(planets_here) == 1:
            # The common case (most houses hold 0 or 1 planet): a real,
            # connected explanation — what's here, how strong it is, what
            # that generally feels like, the concrete effect, and a plain
            # closing line tying it back to the specific life-area asked
            # about, instead of a flat list of disconnected facts.
            p = planets_here[0]
            retro_en = " (retrograde)" if chart.planet_retrograde.get(p) else ""
            retro_hi = " (वक्री)" if chart.planet_retrograde.get(p) else ""
            dignity = planet_dignity(p, chart.planet_sign_index[p]) if p in CLASSICAL_PLANETS else None
            verdict_bucket = _dignity_bucket([dignity])
            effect_en, effect_hi = _planet_effect(p, dignity)
            sentences_en = [f"{names_en[p]}{retro_en} sits in the part of your chart that's about {focus_en[house]}."]
            sentences_hi = [f"{names_hi[p]}{retro_hi} आपकी कुंडली के उस हिस्से में है जो {focus_hi[house]} से जुड़ा है।"]
            if dignity:
                sentences_en.append(f"It is {qualifier_en[dignity]}.")
                sentences_hi.append(f"यह {qualifier_hi[dignity]}।")
            sentences_en.append(f"{names_en[p]} generally brings {_a_or_an(_TONE_BY_LORD_EN[p])} {_TONE_BY_LORD_EN[p]} quality.")
            sentences_hi.append(f"{names_hi[p]} आमतौर पर {_TONE_BY_LORD_HI[p]} भाव लाता है।")
            sentences_en.append(effect_en)
            sentences_hi.append(effect_hi)
            sentences_en.append(f"In {focus_en[house]} specifically, {_PRACTICAL_TIP_EN[p]}.")
            sentences_hi.append(f"खासकर {focus_hi[house]} के मामले में, {_PRACTICAL_TIP_HI[p]}।")
            explanation_en = " ".join(sentences_en)
            explanation_hi = " ".join(sentences_hi)
        else:
            # Multiple planets sharing a house — each gets its own full
            # explanation (placement, tone, effect, practical tip), named
            # so it's clear which sentence belongs to which planet.
            sentences_en, sentences_hi = [], []
            dignities_here: list[str | None] = []
            for p in planets_here:
                retro_en = " (retrograde)" if chart.planet_retrograde.get(p) else ""
                retro_hi = " (वक्री)" if chart.planet_retrograde.get(p) else ""
                dignity = planet_dignity(p, chart.planet_sign_index[p]) if p in CLASSICAL_PLANETS else None
                dignities_here.append(dignity)
                effect_en, effect_hi = _planet_effect(p, dignity)
                placement_en = f"{names_en[p]}{retro_en} is {qualifier_en[dignity]}" if dignity else f"{names_en[p]}{retro_en} is here"
                placement_hi = f"{names_hi[p]}{retro_hi} {qualifier_hi[dignity]}" if dignity else f"{names_hi[p]}{retro_hi} यहां है"
                sentences_en.append(
                    f"{placement_en}, generally bringing {_a_or_an(_TONE_BY_LORD_EN[p])} {_TONE_BY_LORD_EN[p]} "
                    f"quality. {effect_en} In {focus_en[house]} specifically, {_PRACTICAL_TIP_EN[p]}."
                )
                sentences_hi.append(
                    f"{placement_hi}, जो आमतौर पर {_TONE_BY_LORD_HI[p]} भाव लाता है। {effect_hi} "
                    f"खासकर {focus_hi[house]} के मामले में, {_PRACTICAL_TIP_HI[p]}।"
                )

            conjunction_en = (
                f" {_join_and([names_en[p] for p in planets_here])} are conjunct here (sharing the same "
                "house), so their effects blend into one another rather than acting separately."
            )
            conjunction_hi = (
                f" {' और '.join(names_hi[p] for p in planets_here)} एक ही भाव में युति में हैं, इसलिए इनका असर अलग-अलग नहीं "
                "बल्कि आपस में मिला-जुला रहता है।"
            )
            explanation_en = f"This house governs {focus_en[house]}.{conjunction_en} " + " ".join(sentences_en)
            explanation_hi = f"यह भाव {focus_hi[house]} को दर्शाता है।{conjunction_hi} " + " ".join(sentences_hi)
            verdict_bucket = _dignity_bucket(dignities_here)

        this_house_lord = house_lord(house, chart.lagna_sign_index)
        lord_theme_en = planet_themes[this_house_lord]["theme_en"]
        lord_theme_hi = planet_themes[this_house_lord]["theme_hi"]
        breakdown.append(
            {
                "house": house,
                "sign_name_en": SIGN_NAMES_EN[sign_idx],
                "sign_name_hi": SIGN_NAMES_HI[sign_idx],
                "planets": planets_here,
                "explanation_en": explanation_en,
                "explanation_hi": explanation_hi,
                "verdict_en": f"{_VERDICT_BY_HOUSE_EN[house][verdict_bucket]} {_VERDICT_REASON_EN[verdict_bucket]}",
                "verdict_hi": f"{_VERDICT_BY_HOUSE_HI[house][verdict_bucket]} {_VERDICT_REASON_HI[verdict_bucket]}",
                "lord": this_house_lord,
                "lord_theme_en": lord_theme_en,
                "lord_theme_hi": lord_theme_hi,
            }
        )
    return breakdown


def detect_yogas(chart: ChartResult) -> list[dict]:
    """Classically devised for D1 charts; also applied to D9/D10 as the same
    real, placement-based checks against that divisional chart's own sign
    positions — a documented simplification (see chart_service.get_chart),
    not a fabricated fact: whatever this finds is a genuine structural
    pattern in the chart it was given, just not universally endorsed by
    every classical text for non-D1 use."""
    findings = []

    moon_sign = chart.planet_sign_index["Mo"]
    jupiter_sign = chart.planet_sign_index["Ju"]
    if has_gajakesari_yoga(house_number(jupiter_sign, moon_sign)):
        findings.append(
            {
                "key": "gajakesari",
                "name_en": "Gajakesari Yoga",
                "name_hi": "गजकेसरी योग",
                "description_en": (
                    "Moon and Jupiter sit in mutual angular (Kendra) houses — a classical combination for "
                    "a calm, socially respected temperament and generally steady good fortune."
                ),
                "description_hi": (
                    "चंद्रमा और गुरु एक-दूसरे से केंद्र भाव में हैं — यह शांत स्वभाव, सामाजिक सम्मान और "
                    "सामान्यतः स्थिर सौभाग्य का शास्त्रीय संयोग है।"
                ),
                "chat_summary_en": "Yes, you have Gajakesari Yoga — a sign of a calm nature and generally steady good fortune.",
                "chat_summary_hi": "हां, आपकी कुंडली में गजकेसरी योग है — यह शांत स्वभाव और सामान्यतः स्थिर सौभाग्य का संकेत है।",
            }
        )

    dignity_map = {p: planet_dignity(p, chart.planet_sign_index[p]) for p in CLASSICAL_PLANETS}
    for m in compute_panch_mahapurusha_yogas(chart.planet_house, dignity_map):
        findings.append(
            {
                "key": f"mahapurusha_{m.planet.lower()}",
                "name_en": f"{m.name} Yoga",
                "name_hi": f"{MAHAPURUSHA_PLANET_NAMES_HI[m.planet]} योग",
                "description_en": _MAHAPURUSHA_DESCRIPTIONS_EN[m.planet],
                "description_hi": _MAHAPURUSHA_DESCRIPTIONS_HI[m.planet],
                "chat_summary_en": _MAHAPURUSHA_CHAT_SUMMARY_EN[m.planet],
                "chat_summary_hi": _MAHAPURUSHA_CHAT_SUMMARY_HI[m.planet],
            }
        )

    house_lords = {h: house_lord(h, chart.lagna_sign_index) for h in range(1, 13)}
    if has_conservative_raj_yoga(house_lords, chart.planet_house):
        findings.append(
            {
                "key": "raj_yoga",
                "name_en": "Raj Yoga",
                "name_hi": "राज योग",
                "description_en": (
                    "An angular (Kendra) house lord and a trine (Trikona) house lord share the same house — "
                    "a classical Raj Yoga pattern, generally read as a real boost to status and success."
                ),
                "description_hi": (
                    "एक केंद्र भाव का स्वामी और एक त्रिकोण भाव का स्वामी एक ही भाव में हैं — यह प्रतिष्ठा और "
                    "सफलता बढ़ाने वाला शास्त्रीय राज योग है।"
                ),
                "chat_summary_en": "Yes, you have Raj Yoga — a classical boost to status and success.",
                "chat_summary_hi": "हां, आपकी कुंडली में राज योग है — यह प्रतिष्ठा और सफलता को बढ़ावा देने वाला शास्त्रीय योग है।",
            }
        )

    mars_sign = chart.planet_sign_index["Ma"]
    manglik = compute_manglik_facts(
        mars_sign_index=mars_sign, mars_house_from_lagna=chart.planet_house["Ma"], moon_sign_index=moon_sign,
    )
    if manglik.is_manglik:
        findings.append(
            {
                "key": "manglik",
                "name_en": "Manglik (Mangal) Dosha",
                "name_hi": "मंगलिक (मंगल) दोष",
                "description_en": (
                    "Mars sits in one of the houses classically checked for Manglik dosha (1st, 2nd, 4th, 7th, "
                    "8th or 12th from the Lagna). Many families match this carefully against a partner's chart "
                    "before marriage."
                ),
                "description_hi": (
                    "मंगल लग्न से 1, 2, 4, 7, 8 या 12वें भाव में है, जहां परंपरागत रूप से मंगलिक दोष जांचा जाता है। "
                    "कई परिवार विवाह से पहले साथी की कुंडली से इसका सावधानी से मिलान करते हैं।"
                ),
                "chat_summary_en": (
                    "Yes, you are Manglik. This is something many families check carefully when matching "
                    "charts before marriage."
                ),
                "chat_summary_hi": (
                    "हां, आप मंगलिक हैं। शादी से पहले परिवार अक्सर साथी की कुंडली से इसका सावधानी से मिलान करते हैं।"
                ),
            }
        )

    rahu_sign, ketu_sign = chart.planet_sign_index["Ra"], chart.planet_sign_index["Ke"]
    kaal_sarp = compute_kaal_sarp_dosha(
        lagna_sign_index=chart.lagna_sign_index, rahu_sign_index=rahu_sign, ketu_sign_index=ketu_sign,
        planet_sign_index={p: chart.planet_sign_index[p] for p in CLASSICAL_PLANETS},
    )
    if kaal_sarp.is_present:
        findings.append(
            {
                "key": "kaal_sarp",
                "name_en": "Kaal Sarp Dosha",
                "name_hi": "कालसर्प दोष",
                "description_en": (
                    "All seven classical planets fall on one side of the Rahu-Ketu axis — a classical Kaal Sarp "
                    "pattern, often read as intense, all-or-nothing life themes rather than steady, gradual ones."
                ),
                "description_hi": (
                    "सभी सात मुख्य ग्रह राहु-केतु अक्ष के एक ही ओर हैं — यह तीव्र, सब-कुछ-या-कुछ-नहीं जैसी जीवन "
                    "प्रवृत्तियों से जुड़ा शास्त्रीय कालसर्प दोष है।"
                ),
                "chat_summary_en": (
                    "Yes, you have Kaal Sarp Dosha — classically linked to intense, all-or-nothing life "
                    "patterns rather than slow and steady ones."
                ),
                "chat_summary_hi": (
                    "हां, आपकी कुंडली में कालसर्प दोष है — यह तीव्र, सब-कुछ-या-कुछ-नहीं जैसी जीवन प्रवृत्तियों से "
                    "जुड़ा होता है।"
                ),
            }
        )

    kemadruma = compute_kemadruma_dosha(
        planet_house_from_moon={
            p: house_number(chart.planet_sign_index[p], moon_sign) for p in CLASSICAL_PLANETS if p != "Mo"
        }
    )
    if kemadruma.is_present:
        findings.append(
            {
                "key": "kemadruma",
                "name_en": "Kemadruma Dosha",
                "name_hi": "केमद्रुम दोष",
                "description_en": (
                    "No planet supports the Moon from an adjacent or angular house — a classical Kemadruma "
                    "pattern, sometimes read as emotional isolation unless other strong placements offset it."
                ),
                "description_hi": (
                    "चंद्रमा को किसी भी निकटवर्ती या केंद्र भाव से किसी ग्रह का समर्थन नहीं है — यह भावनात्मक "
                    "अकेलेपन से जुड़ा शास्त्रीय केमद्रुम दोष है, जब तक अन्य मज़बूत स्थितियां इसे संतुलित न करें।"
                ),
                "chat_summary_en": (
                    "Yes, you have Kemadruma Dosha — classically linked to feeling emotionally isolated at "
                    "times, unless other strong placements balance it out."
                ),
                "chat_summary_hi": (
                    "हां, आपकी कुंडली में केमद्रुम दोष है — यह कभी-कभी भावनात्मक अकेलापन महसूस होने से जुड़ा है, "
                    "जब तक अन्य मज़बूत स्थितियां इसे संतुलित न करें।"
                ),
            }
        )

    return findings
