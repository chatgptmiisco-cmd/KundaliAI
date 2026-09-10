"""Deterministic, no-LLM text composition for the Prediction Engine (year
outlook, marriage timing, and life-event timing — career/wealth/children/
foreign travel). Standalone functions, deliberately NOT part of
the `Interpreter` ABC/factory (see app.services.interpretation.factory) — a
prediction is astrology's own computed facts turned into plain language, and
must stay rule-based even if the app's other prose (chat replies, etc.) is
ever switched to an LLM interpreter. Reuses the same multi-fact compositional
style as `complete_kundali` in app.services.interpretation.templates (lord +
house + dignity + focus-area, not a single canned per-planet lookup) so two
different years or charts produce genuinely different text.
"""
from typing import Any, Literal

from app.astro.constants import PLANET_NAMES_EN, PLANET_NAMES_HI, PlanetKey
from app.services.interpretation.templates import (
    _DIGNITY_QUALIFIER_EN,
    _DIGNITY_QUALIFIER_HI,
    _FOCUS_BY_HOUSE_EN,
    _FOCUS_BY_HOUSE_HI,
    _PERIOD_CONTENT_EN,
    _PERIOD_CONTENT_HI,
    _hindi_house,
    _ordinal,
)

Language = Literal["en", "hi"]
Dignity = Literal["exalted", "debilitated", "own_sign", "neutral"]

_DIGNITY_POINTS: dict[Dignity, int] = {"exalted": 3, "own_sign": 2, "neutral": 0, "debilitated": -3}
_SUPPORTIVE_HOUSES = {1, 2, 4, 5, 7, 9, 10, 11}
_CHALLENGING_HOUSES = {6, 8, 12}


def year_rating(
    antardasha_lord_dignity: Dignity, varsheshwar_dignity: Dignity, muntha_house: int, active_dosha_count: int
) -> int:
    """Combines the running Antardasha lord's natal dignity (the dominant,
    full-weight signal — this is what's actually active), the year's
    Varsheshwar's natal dignity (a half-weight backdrop signal — it colors
    the whole year, not just this stretch of it), whether the Muntha lands
    in a classically supportive or difficult house, and how many real doshas
    (e.g. an active Sade Sati phase) are in effect, into a single 1-10 score."""
    score = 5
    score += _DIGNITY_POINTS[antardasha_lord_dignity]
    score += _DIGNITY_POINTS[varsheshwar_dignity] // 2
    if muntha_house in _SUPPORTIVE_HOUSES:
        score += 1
    elif muntha_house in _CHALLENGING_HOUSES:
        score -= 1
    score -= active_dosha_count
    return max(1, min(10, score))


def year_outlook_text(
    antardasha_lord: PlanetKey,
    antardasha_lord_house: int,
    antardasha_lord_dignity: Dignity,
    varsheshwar: PlanetKey,
    varsheshwar_dignity: Dignity,
    muntha_house: int,
    jupiter_transit_house_from_moon: int,
    saturn_transit_house_from_moon: int,
    active_dosha_notes: list[str],
    language: Language,
) -> dict[str, Any]:
    """Returns {theme, rating, opportunities, risks} for one quarter/stretch
    of a year-ahead outlook, composed from real natal + Varshaphala facts —
    never a single canned per-planet block.

    A single Antardasha commonly runs an entire year (some last several
    years), which would otherwise make every quarter in that year read
    identically. Jupiter and Saturn's own slow transit-house-from-Moon
    genuinely does shift quarter to quarter even then, so folding it in here
    keeps each quarter's text tied to something that's actually different
    about that specific stretch, not just repeated dasha framing."""
    hi = language == "hi"
    names = PLANET_NAMES_HI if hi else PLANET_NAMES_EN
    qualifier = _DIGNITY_QUALIFIER_HI if hi else _DIGNITY_QUALIFIER_EN
    focus = _FOCUS_BY_HOUSE_HI if hi else _FOCUS_BY_HOUSE_EN
    house_word = (lambda h: _hindi_house(h)) if hi else (lambda h: f"{_ordinal(h)} house")

    antar_name = names[antardasha_lord]
    varsh_name = names[varsheshwar]
    jupiter_name = names["Ju"]
    saturn_name = names["Sa"]

    if hi:
        theme = (
            f"यह अवधि आपकी {antar_name} अंतर्दशा में चल रही है, जो आपके {house_word(antardasha_lord_house)} से "
            f"{qualifier[antardasha_lord_dignity]} — इसलिए {focus[antardasha_lord_house]} पर सबसे ज़्यादा असर पड़ेगा। "
            f"इस वर्ष के स्वामी (वर्षेश्वर) {varsh_name} आपकी जन्म कुंडली में {qualifier[varsheshwar_dignity]}। "
            f"मुंथा आपके {house_word(muntha_house)} में है, जो {focus[muntha_house]} को उजागर करता है। "
            f"इस दौरान {jupiter_name} आपके चंद्र राशि से {house_word(jupiter_transit_house_from_moon)} में गोचर कर रहा है "
            f"({focus[jupiter_transit_house_from_moon]} पर असर), और {saturn_name} आपके चंद्र राशि से "
            f"{house_word(saturn_transit_house_from_moon)} में ({focus[saturn_transit_house_from_moon]} पर असर)।"
        )
    else:
        theme = (
            f"This stretch runs under your {antar_name} Antardasha, {qualifier[antardasha_lord_dignity]} from your "
            f"{house_word(antardasha_lord_house)} — so {focus[antardasha_lord_house]} is what's most affected. "
            f"{varsh_name}, this year's ruling planet (Varsheshwar), is {qualifier[varsheshwar_dignity]} in your "
            f"natal chart. The Muntha falls in your {house_word(muntha_house)}, highlighting {focus[muntha_house]}. "
            f"During this stretch, {jupiter_name} transits your {house_word(jupiter_transit_house_from_moon)} from "
            f"the Moon (touching {focus[jupiter_transit_house_from_moon]}), and {saturn_name} transits your "
            f"{house_word(saturn_transit_house_from_moon)} (touching {focus[saturn_transit_house_from_moon]})."
        )

    opportunities: list[str] = []
    risks: list[str] = []

    if antardasha_lord_dignity in ("exalted", "own_sign"):
        opportunities.append(
            f"{antar_name} की मज़बूत स्थिति की वजह से {focus[antardasha_lord_house]} में असली मौका है — आगे बढ़ने का अच्छा समय।"
            if hi else
            f"Real strength in {focus[antardasha_lord_house]} right now, thanks to {antar_name}'s strong placement — a good window to push forward there."
        )
    elif antardasha_lord_dignity == "debilitated":
        risks.append(
            f"{focus[antardasha_lord_house]} को इस दौरान अतिरिक्त धैर्य चाहिए — {antar_name} यहां दबाव में है।"
            if hi else
            f"{focus[antardasha_lord_house].capitalize()} needs extra patience during this stretch — {antar_name} is under real strain here."
        )
    else:
        opportunities.append(
            f"{antar_name} की स्थिति यहां साधारण है — इस पहलू से न बड़ा फ़ायदा, न बड़ी रुकावट।"
            if hi else
            f"{antar_name}'s placement here is steady but unremarkable — no major boost or drag from this factor."
        )

    if muntha_house in _SUPPORTIVE_HOUSES:
        opportunities.append(
            f"मुंथा का {house_word(muntha_house)} में होना {focus[muntha_house]} के लिए सहयोगी माना जाता है।"
            if hi else
            f"The Muntha in your {house_word(muntha_house)} is classically supportive for {focus[muntha_house]}."
        )
    elif muntha_house in _CHALLENGING_HOUSES:
        risks.append(
            f"मुंथा का {house_word(muntha_house)} में होना इस साल {focus[muntha_house]} में सावधानी बरतने का संकेत देता है।"
            if hi else
            f"The Muntha in your {house_word(muntha_house)} is a classical caution flag around {focus[muntha_house]} this year."
        )

    if jupiter_transit_house_from_moon in _SUPPORTIVE_HOUSES:
        opportunities.append(
            f"गुरु का गोचर आपके {house_word(jupiter_transit_house_from_moon)} में {focus[jupiter_transit_house_from_moon]} के लिए शुभ माना जाता है।"
            if hi else
            f"Jupiter's transit through your {house_word(jupiter_transit_house_from_moon)} is classically favorable for {focus[jupiter_transit_house_from_moon]}."
        )
    if saturn_transit_house_from_moon in _CHALLENGING_HOUSES:
        risks.append(
            f"शनि का गोचर आपके {house_word(saturn_transit_house_from_moon)} में {focus[saturn_transit_house_from_moon]} में सतर्क, धीमी प्रगति का संकेत देता है।"
            if hi else
            f"Saturn's transit through your {house_word(saturn_transit_house_from_moon)} calls for slow, careful progress around {focus[saturn_transit_house_from_moon]}."
        )

    risks.extend(active_dosha_notes)

    rating = year_rating(antardasha_lord_dignity, varsheshwar_dignity, muntha_house, len(active_dosha_notes))
    return {"theme": theme, "rating": rating, "opportunities": opportunities, "risks": risks}


def overall_year_theme(varsheshwar: PlanetKey, varsheshwar_dignity: Dignity, muntha_house: int, language: Language) -> str:
    """A whole-year framing sentence built only from the Varshaphala facts
    (Varsheshwar + Muntha) — distinct from each quarter's theme, which is
    additionally driven by whichever Antardasha is running that quarter."""
    hi = language == "hi"
    names = PLANET_NAMES_HI if hi else PLANET_NAMES_EN
    qualifier = _DIGNITY_QUALIFIER_HI if hi else _DIGNITY_QUALIFIER_EN
    focus = _FOCUS_BY_HOUSE_HI if hi else _FOCUS_BY_HOUSE_EN
    house_word = (lambda h: _hindi_house(h)) if hi else (lambda h: f"{_ordinal(h)} house")
    name = names[varsheshwar]

    if hi:
        return (
            f"इस वर्ष के स्वामी (वर्षेश्वर) {name} आपकी जन्म कुंडली में {qualifier[varsheshwar_dignity]}, "
            f"जो पूरे साल का माहौल तय करता है। मुंथा आपके {house_word(muntha_house)} में है, इसलिए "
            f"{focus[muntha_house]} इस साल का केंद्र-बिंदु बनता है।"
        )
    return (
        f"{name}, this year's ruling planet (Varsheshwar), is {qualifier[varsheshwar_dignity]} in your natal "
        f"chart — setting the overall tone for the year. The Muntha falls in your {house_word(muntha_house)}, "
        f"making {focus[muntha_house]} the year's central focus."
    )


# Deliberately plain-language, no "Antardasha"/"Mahadasha"/"7th-house lord"
# jargon — the real computed fact worth keeping is WHICH planet and WHY it
# matters for relationships, not the Sanskrit name for the time-period
# mechanism. See marriage_window_reason_text below: this is only the "why"
# half of the answer, which now LEADS with a real plain-language effect
# (that planet's own _PERIOD_CONTENT one-liner) instead.
_MARRIAGE_REASON_EN: dict[str, str] = {
    "seventh_lord_antardasha": "{lord} — the planet most tied to your relationships — has extra pull during this phase.",
    "venus_antardasha": "Venus, the planet most linked to love and connection, is especially active in this phase.",
    "jupiter_antardasha": "Jupiter, the planet most linked to a life partner, is especially active in this phase.",
    "seventh_lord_mahadasha": "This whole stretch runs under a longer period led by {lord}, the planet most tied to your relationships.",
    "venus_mahadasha": "This whole stretch runs under a longer period led by Venus, keeping love and connection in focus.",
    "jupiter_mahadasha": "This whole stretch runs under a longer period led by Jupiter, keeping partnership themes in focus.",
}
_MARRIAGE_REASON_HI: dict[str, str] = {
    "seventh_lord_antardasha": "{lord} — आपके रिश्तों से सबसे ज़्यादा जुड़ा ग्रह — इस दौर में विशेष रूप से सक्रिय है।",
    "venus_antardasha": "प्रेम और जुड़ाव से जुड़ा ग्रह शुक्र इस दौर में विशेष रूप से सक्रिय है।",
    "jupiter_antardasha": "जीवनसाथी से जुड़ा ग्रह गुरु इस दौर में विशेष रूप से सक्रिय है।",
    "seventh_lord_mahadasha": "यह पूरी अवधि {lord} की एक बड़ी अवधि के अंतर्गत आती है — आपके रिश्तों से सबसे ज़्यादा जुड़ा ग्रह।",
    "venus_mahadasha": "यह पूरी अवधि शुक्र की एक बड़ी अवधि के अंतर्गत आती है, जिससे प्रेम और जुड़ाव पर ध्यान बना रहता है।",
    "jupiter_mahadasha": "यह पूरी अवधि गुरु की एक बड़ी अवधि के अंतर्गत आती है, जिससे साझेदारी के विषय केंद्र में रहते हैं।",
}
_TRANSIT_CORROBORATION_EN = "Jupiter or Saturn are also passing through the part of your chart tied to relationships during this window — a second real signal pointing the same way."
_TRANSIT_CORROBORATION_HI = "इस अवधि के दौरान गुरु या शनि भी आपकी कुंडली के रिश्तों वाले हिस्से से गुज़र रहे हैं — यह उसी दिशा में एक और वास्तविक संकेत है।"

# Converts the present-tense reason sentences above into past tense for a
# window that's already elapsed ("had extra pull", not "has extra pull") —
# a fixed, known substitution list (not a heuristic guess) since every
# source phrase above is hand-written and controlled right here.
_TENSE_REPLACEMENTS_EN: list[tuple[str, str]] = [
    ("has extra pull during this phase", "had extra pull during that phase"),
    ("is especially active in this phase", "was especially active in that phase"),
    ("This whole stretch runs under", "That whole stretch ran under"),
    ("This stretch runs under", "That stretch ran under"),
    ("are also passing through the part of your chart tied to relationships during this window", "also passed through the part of your chart tied to relationships during that window"),
    ("are also passing through", "also passed through"),
    ("is also passing through", "also passed through"),
    ("during this window", "during that window"),
]
_TENSE_REPLACEMENTS_HI: list[tuple[str, str]] = [
    ("सक्रिय है", "सक्रिय था"),
    ("अंतर्गत आती है", "अंतर्गत आई थी"),
    ("गुज़र रहे हैं", "गुज़र रहे थे"),
    ("गुज़र रहा है", "गुज़रा था"),
    ("इस अवधि के दौरान", "उस अवधि के दौरान"),
    ("इस दौर में", "उस दौर में"),
]


def _apply_past_tense(text: str, hi: bool) -> str:
    for old, new in (_TENSE_REPLACEMENTS_HI if hi else _TENSE_REPLACEMENTS_EN):
        text = text.replace(old, new)
    return text


def marriage_window_reason_text(
    reason_keys: list[str],
    seventh_lord_name: str,
    antardasha_lord: PlanetKey,
    transit_corroborated: bool,
    language: Language,
    tense: Literal["past", "future"] = "future",
) -> str:
    """Leads with a real, plain-language EFFECT (the running planet's own
    classical one-liner, already written for period_analysis — honest,
    tested, jargon-free) before the "why" mechanism explanation, instead of
    opening with Sanskrit period-names a reader has to already know."""
    hi = language == "hi"
    pool = _MARRIAGE_REASON_HI if hi else _MARRIAGE_REASON_EN
    content_pool = _PERIOD_CONTENT_HI if hi else _PERIOD_CONTENT_EN
    effect = content_pool.get(antardasha_lord, content_pool["Mo"])["one_liner"]

    sentences = [pool[k].format(lord=seventh_lord_name) for k in reason_keys]
    mechanism = " ".join(sentences)
    if transit_corroborated:
        mechanism += " " + (_TRANSIT_CORROBORATION_HI if hi else _TRANSIT_CORROBORATION_EN)
    if tense == "past":
        mechanism = _apply_past_tense(mechanism, hi)
    return f"{effect} {mechanism}"


# --- Life-event timing (career/wealth/children/foreign_travel) reason text -
# Generic version of the marriage-reason composer above, parametrized by
# event type — see app.astro.life_event_timing for the matching rule/reason
# keys (f"{event_type}_house_lord_antardasha" etc.) this parses.

_EVENT_HOUSE_PHRASE_EN: dict[str, str] = {
    "career": "your 10th house of career", "wealth": "your 2nd house of wealth",
    "children": "your 5th house of children", "foreign_travel": "your 12th house of foreign lands",
}
_EVENT_HOUSE_PHRASE_HI: dict[str, str] = {
    "career": "आपके करियर के दसवें भाव", "wealth": "आपके धन के दूसरे भाव",
    "children": "आपकी संतान के पांचवें भाव", "foreign_travel": "आपके विदेश के बारहवें भाव",
}
# Per-(event, karaka) framing — the SAME planet means something different
# depending which event it's a karaka for (Jupiter is the children karaka
# here, a wealth significator there), so this is keyed by pair, not by
# planet alone. Name and description are kept SEPARATE (not one combined
# comma-appositive string) so the Mahadasha sentence can attach "'s broader
# Mahadasha" to the bare planet name — appending it after a full appositive
# phrase ("Rahu, the significator of foreign lands and relocation's broader
# Mahadasha") reads as though "relocation" possesses the Mahadasha, not Rahu.
_EVENT_KARAKA_NAME_EN: dict[tuple[str, str], str] = {
    ("career", "Sa"): "Saturn", ("career", "Su"): "the Sun",
    ("wealth", "Ju"): "Jupiter", ("wealth", "Ve"): "Venus",
    ("children", "Ju"): "Jupiter",
    ("foreign_travel", "Ra"): "Rahu", ("foreign_travel", "Ju"): "Jupiter",
}
_EVENT_KARAKA_NAME_HI: dict[tuple[str, str], str] = {
    ("career", "Sa"): "शनि", ("career", "Su"): "सूर्य",
    ("wealth", "Ju"): "गुरु", ("wealth", "Ve"): "शुक्र",
    ("children", "Ju"): "गुरु",
    ("foreign_travel", "Ra"): "राहु", ("foreign_travel", "Ju"): "गुरु",
}
_EVENT_KARAKA_DESC_EN: dict[tuple[str, str], str] = {
    ("career", "Sa"): "your karma/profession karaka",
    ("career", "Su"): "the karaka for authority and status",
    ("wealth", "Ju"): "a classical wealth significator",
    ("wealth", "Ve"): "a classical wealth significator",
    ("children", "Ju"): "the classical santan (children) karaka",
    ("foreign_travel", "Ra"): "the classical significator of foreign lands and relocation",
    ("foreign_travel", "Ju"): "co-significator of long journeys",
}
_EVENT_KARAKA_DESC_HI: dict[tuple[str, str], str] = {
    ("career", "Sa"): "आपका कर्म/पेशा कारक",
    ("career", "Su"): "अधिकार और प्रतिष्ठा का कारक",
    ("wealth", "Ju"): "धन का एक शास्त्रीय कारक",
    ("wealth", "Ve"): "धन का एक शास्त्रीय कारक",
    ("children", "Ju"): "संतान का शास्त्रीय कारक",
    ("foreign_travel", "Ra"): "विदेश और स्थानांतरण का शास्त्रीय कारक",
    ("foreign_travel", "Ju"): "लंबी यात्राओं का सह-कारक",
}
_EVENT_TRANSIT_CORROBORATION_EN = "A relevant planet is also passing through {house} during this window — a second real signal pointing the same way."
_EVENT_TRANSIT_CORROBORATION_HI = "इस अवधि के दौरान एक संबंधित ग्रह भी {house} से गुज़र रहा है — यह उसी दिशा में एक और वास्तविक संकेत है।"


def life_event_reason_text(
    event_type: str,
    reason_keys: list[str],
    house_lord_name: str,
    antardasha_lord: PlanetKey,
    transit_corroborated: bool,
    language: Language,
    tense: Literal["past", "future"] = "future",
) -> str:
    """Leads with a real, plain-language EFFECT (the running planet's own
    classical one-liner) before the "why" mechanism sentences, mirroring
    marriage_window_reason_text above — no Sanskrit period-names up front."""
    hi = language == "hi"
    house_phrase = (_EVENT_HOUSE_PHRASE_HI if hi else _EVENT_HOUSE_PHRASE_EN)[event_type]
    karaka_names = _EVENT_KARAKA_NAME_HI if hi else _EVENT_KARAKA_NAME_EN
    karaka_descs = _EVENT_KARAKA_DESC_HI if hi else _EVENT_KARAKA_DESC_EN
    content_pool = _PERIOD_CONTENT_HI if hi else _PERIOD_CONTENT_EN
    effect = content_pool.get(antardasha_lord, content_pool["Mo"])["one_liner"]

    sentences: list[str] = []
    for key in reason_keys:
        if key == f"{event_type}_house_lord_antardasha":
            sentences.append(
                f"{house_lord_name} — {house_phrase} से सबसे ज़्यादा जुड़ा ग्रह — इस दौर में विशेष रूप से सक्रिय है।"
                if hi else
                f"{house_lord_name} — the planet most tied to {house_phrase} — has extra pull during this phase."
            )
        elif key == f"{event_type}_house_lord_mahadasha":
            sentences.append(
                f"यह पूरी अवधि {house_lord_name} की एक बड़ी अवधि के अंतर्गत आती है, जिससे {house_phrase} पर ध्यान बना रहता है।"
                if hi else
                f"This whole stretch runs under a longer period led by {house_lord_name}, keeping {house_phrase} in focus."
            )
        elif key.startswith(f"{event_type}_karaka_antardasha_"):
            karaka = key.rsplit("_", 1)[-1]
            name, desc = karaka_names[(event_type, karaka)], karaka_descs[(event_type, karaka)]
            sentences.append(
                f"{name} — {desc} — इस दौर में विशेष रूप से सक्रिय है।" if hi else
                f"{name} — {desc} — is especially active in this phase."
            )
        elif key.startswith(f"{event_type}_karaka_mahadasha_"):
            karaka = key.rsplit("_", 1)[-1]
            name, desc = karaka_names[(event_type, karaka)], karaka_descs[(event_type, karaka)]
            sentences.append(
                f"यह अवधि {name} ({desc}) की एक बड़ी अवधि के अंतर्गत आती है।"
                if hi else
                f"This stretch runs under a longer period led by {name} ({desc})."
            )

    mechanism = " ".join(sentences)
    if transit_corroborated:
        template = _EVENT_TRANSIT_CORROBORATION_HI if hi else _EVENT_TRANSIT_CORROBORATION_EN
        mechanism += " " + template.format(house=house_phrase)
    if tense == "past":
        mechanism = _apply_past_tense(mechanism, hi)
    return f"{effect} {mechanism}"


# --- Life theme reflection (general "what was going on then") -------------
# Retrospective narration for ANY date (past, present, or future), not tied
# to one specific life-event type — reuses the SAME per-lord classical
# content already written for forward-looking period analysis
# (_PERIOD_CONTENT_EN/HI in templates.py), just framed as a real, computed
# thematic TENDENCY rather than a fabricated specific claim: "this period is
# classically associated with X", never "you experienced X". This is the
# honest version of what real astrologers do when narrating a client's past
# — the Dasha/Sade-Sati/Dhaiya facts are 100% real and computed; only the
# generic signification set is being named, not an invented event.


def life_theme_text(
    mahadasha_lord: PlanetKey,
    antardasha_lord: PlanetKey,
    sade_sati_active: bool,
    dhaiya_active: bool,
    language: Language,
) -> dict[str, Any]:
    hi = language == "hi"
    names = PLANET_NAMES_HI if hi else PLANET_NAMES_EN
    pool = _PERIOD_CONTENT_HI if hi else _PERIOD_CONTENT_EN
    maha_content = pool.get(mahadasha_lord, pool["Mo"])
    antar_content = pool.get(antardasha_lord, pool["Mo"])
    maha_name = names[mahadasha_lord]
    antar_name = names[antardasha_lord]

    # Same 2:1 antardasha-weighted blend as period_analysis (templates.py) —
    # the immediate lord dominates lived experience, the mahadasha only sets
    # backdrop.
    rating = round((maha_content["rating"] + 2 * antar_content["rating"]) / 3)

    if hi:
        theme = (
            f"उस समय {antar_name} का दौर सबसे ज़्यादा हावी था (और उसके पीछे {maha_name} का बड़ा असर भी था)। "
            f"ऐसे दौर में आमतौर पर यह देखने को मिलता है: {antar_content['one_liner']}"
        )
    else:
        theme = (
            f"{antar_name} was the dominant influence at that time, with {maha_name} shaping the "
            f"broader backdrop. A period like this classically tends to bring: {antar_content['one_liner']}"
        )

    hardship_notes = []
    if sade_sati_active:
        hardship_notes.append(
            "इस दौरान शनि की साढ़े साती भी सक्रिय थी — यह आमतौर पर संघर्ष, देरी और सामान्य से ज़्यादा भारीपन से जुड़ी होती है।"
            if hi else
            "Saturn's Sade Sati was also active during this window — classically linked to hardship, "
            "delay, and a heavier load than usual."
        )
        rating = max(1, rating - 1)
    if dhaiya_active:
        hardship_notes.append(
            "शनि की ढैया भी इसी दौरान सक्रिय थी — यह भी एक जाना-पहचाना कठिन दौर माना जाता है।"
            if hi else
            "Saturn's Dhaiya was also active then — another classically recognized difficult stretch."
        )
        rating = max(1, rating - 1)
    if hardship_notes:
        theme += " " + " ".join(hardship_notes)

    return {"theme": theme, "rating": max(1, min(10, rating))}
