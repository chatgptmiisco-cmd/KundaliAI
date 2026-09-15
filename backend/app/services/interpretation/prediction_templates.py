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

# Surfaces the SAME natal-strength signal that already scales the window's
# rank (see app.astro.natal_insights.significator_strength and
# prediction_service._significator_strength) as plain language, instead of
# only ever affecting ranking invisibly. Deliberately silent for the
# "neither clearly strong nor clearly weak" middle ground — a note on every
# single window would read as noise, not signal.
NatalStrength = Literal["strong", "weak"]
_NATAL_STRENGTH_EN: dict[NatalStrength, str] = {
    "strong": "{name} is also well-placed in your birth chart itself (dignified, unafflicted) — a genuinely stronger version of this signal, not just a favorable dasha label.",
    "weak": "{name} is weakly placed in your birth chart itself (afflicted or debilitated) — so treat this window as a real but comparatively softer signal.",
}
_NATAL_STRENGTH_HI: dict[NatalStrength, str] = {
    "strong": "{name} आपकी जन्म कुंडली में भी मज़बूत स्थिति में है (सशक्त, बिना किसी दोष के) — यह सिर्फ़ दशा का नाम नहीं बल्कि वाकई एक मज़बूत संकेत है।",
    "weak": "{name} आपकी जन्म कुंडली में कमज़ोर स्थिति में है (पीड़ित या नीच) — इसलिए इसे एक वास्तविक लेकिन अपेक्षाकृत हल्का संकेत मानें।",
}

# Surfaces a real, already-computed fact (see app.astro.charts's
# planet_retrograde, threaded through prediction_service._significator_
# retrograde) that the Prediction Engine never mentioned anywhere before —
# purely informational, NEVER folded into score/ranking, because classical
# sources genuinely disagree on whether retrograde strengthens a planet
# (Shadbala's Cheshta Bala) or weakens/delays it (the far more common
# everyday reading). Taking a side here would be a guess dressed up as a
# computed fact, so this only ever states the fact and lets the reader
# weigh it — same honesty rule as every documented simplification in
# app.astro (see e.g. app.astro.guna_milan's module docstring).
_RETROGRADE_NOTE_EN = "{name} is also retrograde right now — classical opinions differ on what that means here (some read it as extra intensity, others as delay or revisiting old ground), so take it as one more real data point, not a verdict."
_RETROGRADE_NOTE_HI = "{name} फ़िलहाल वक्री (retrograde) भी है — इसका ठीक-ठीक क्या मतलब है, इस पर शास्त्रीय राय बंटी हुई है (कुछ इसे अतिरिक्त तीव्रता मानते हैं, कुछ देरी या पुरानी बातों की वापसी) — इसलिए इसे एक निर्णय नहीं, बल्कि एक और असली तथ्य समझें।"

# Surfaces app.astro.transit_corroboration's OBSTRUCTION signal: a different
# malefic actually transiting THROUGH the same house during this window —
# independent of (and can coexist with) a positive Jupiter/Saturn or karaka
# corroboration above. A real, separate classical caution, not a
# contradiction of the corroboration note.
_TRANSIT_OBSTRUCTION_EN = "At the same time, {planet} is also transiting through that same part of your chart — a real caution flag alongside the corroboration above, not a contradiction of it."
_TRANSIT_OBSTRUCTION_HI = "इसी दौरान {planet} भी आपकी कुंडली के उसी हिस्से से गुज़र रहा है — यह ऊपर के संकेत के साथ-साथ एक वास्तविक सतर्कता का संकेत है, उसका खंडन नहीं।"

# Surfaces app.astro.life_stage_plausibility's real-world (NOT classical)
# age-sanity factor, which already scales this window's score down — see
# that module's docstring for why it exists: a chart's own infancy or deep
# old age could otherwise mathematically outrank a sensible-age window
# purely on dasha math, with nothing to say "a newborn can't have a career."
# Deliberately honest about being a non-classical caveat, not a Sanskrit-
# sourced rule like every other note in this file.
_AGE_IMPLAUSIBILITY_EN: dict[str, str] = {
    "early": "This window falls earlier in life than {event} typically happens — a real classical signal, but treat it as a lower-confidence one rather than a literal prediction at that age.",
    "late": "This window falls later in life than {event} typically happens — a real classical signal, but treat it as a lower-confidence one rather than a literal prediction at that age.",
}
_AGE_IMPLAUSIBILITY_HI: dict[str, str] = {
    "early": "यह अवधि उस सामान्य उम्र से पहले की है जब आमतौर पर {event} होता है — यह एक वास्तविक शास्त्रीय संकेत है, पर इसे उस उम्र में शाब्दिक भविष्यवाणी नहीं, बल्कि एक कम-भरोसेमंद संकेत मानें।",
    "late": "यह अवधि उस सामान्य उम्र के बाद की है जब आमतौर पर {event} होता है — यह एक वास्तविक शास्त्रीय संकेत है, पर इसे उस उम्र में शाब्दिक भविष्यवाणी नहीं, बल्कि एक कम-भरोसेमंद संकेत मानें।",
}

_EVENT_LABEL_EN: dict[str, str] = {
    "marriage": "marriage", "career": "a career shift", "wealth": "wealth growth",
    "children": "having children", "foreign_travel": "foreign travel or relocation",
}
_EVENT_LABEL_HI: dict[str, str] = {
    "marriage": "विवाह", "career": "करियर में बदलाव", "wealth": "धन वृद्धि",
    "children": "संतान होना", "foreign_travel": "विदेश यात्रा या स्थानांतरण",
}


def _age_implausibility_sentence(event_key: str, implausibility: Literal["early", "late"] | None, hi: bool) -> str | None:
    if implausibility is None:
        return None
    pool = _AGE_IMPLAUSIBILITY_HI if hi else _AGE_IMPLAUSIBILITY_EN
    labels = _EVENT_LABEL_HI if hi else _EVENT_LABEL_EN
    return pool[implausibility].format(event=labels[event_key])


# A literal reading of the event (an actual first marriage, an actual
# childbirth, independently-earned personal wealth) stops making real-world
# sense at a hard-implausible age (see
# app.astro.life_stage_plausibility.is_hard_implausible_age) regardless of
# how strong the classical dasha signal is — this is stronger than
# `_age_implausibility_sentence` above (which still presents the window as a
# literal, just lower-confidence, prediction). Reached only when
# prediction_service couldn't find any plausible-age alternative anywhere in
# the search horizon, so the honest move is to reinterpret what kind of
# activation this window plausibly represents instead of stating the
# literal event as the answer.
_REINTERPRETATION_EN: dict[str, str] = {
    "marriage": (
        "No astrologically plausible window for a literal first marriage was found nearby, so read this less as "
        "a marriage date and more as a relationship or partnership-related development."
    ),
    "career": (
        "No astrologically plausible window for a typical career shift was found nearby, so read this less as a "
        "literal new career and more as a change in responsibility or role."
    ),
    "wealth": (
        "Independently-earned personal wealth isn't a realistic reading at this age, so read this more as family "
        "finances or shared household resources than your own personal wealth."
    ),
    "children": (
        "A literal childbirth isn't a realistic reading at this age, so read this more as a family or "
        "children's-welfare responsibility than a new child."
    ),
    "foreign_travel": (
        "Independent travel isn't a realistic reading at this age, so read this more as a family-driven "
        "relocation or travel decision than your own trip."
    ),
}
_REINTERPRETATION_HI: dict[str, str] = {
    "marriage": (
        "आस-पास पहली शादी के लिए कोई ज्योतिषीय रूप से उपयुक्त अवधि नहीं मिली, इसलिए इसे शादी की तारीख के बजाय "
        "रिश्ते या साझेदारी से जुड़े किसी विकास के रूप में देखें।"
    ),
    "career": (
        "आस-पास सामान्य करियर बदलाव के लिए कोई ज्योतिषीय रूप से उपयुक्त अवधि नहीं मिली, इसलिए इसे नए करियर के "
        "बजाय ज़िम्मेदारी या भूमिका में बदलाव के रूप में देखें।"
    ),
    "wealth": (
        "इस उम्र में स्वयं अर्जित निजी धन एक व्यावहारिक व्याख्या नहीं है, इसलिए इसे अपने निजी धन के बजाय पारिवारिक "
        "वित्त या साझा घरेलू संसाधनों के रूप में देखें।"
    ),
    "children": (
        "इस उम्र में साक्षात संतान होना एक व्यावहारिक व्याख्या नहीं है, इसलिए इसे नई संतान के बजाय पारिवारिक या "
        "बच्चों की भलाई से जुड़ी ज़िम्मेदारी के रूप में देखें।"
    ),
    "foreign_travel": (
        "इस उम्र में स्वतंत्र यात्रा एक व्यावहारिक व्याख्या नहीं है, इसलिए इसे अपनी यात्रा के बजाय परिवार-प्रेरित "
        "स्थानांतरण या यात्रा-निर्णय के रूप में देखें।"
    ),
}


def _reinterpretation_sentence(event_key: str, literal_event_plausible: bool, hi: bool) -> str | None:
    if literal_event_plausible:
        return None
    return (_REINTERPRETATION_HI if hi else _REINTERPRETATION_EN)[event_key]


# Surfaced when prediction_service._select_candidate_pool couldn't find any
# window whose OWN Antardasha is the house lord or a karaka anywhere in the
# search horizon, so it fell back to one that only qualifies through its
# broader Mahadasha (evidence_level == "backdrop_only" — see
# prediction_service._evidence_level) — a real but comparatively weak
# signal, since nothing about this specific narrower phase itself ties it
# to the event. Deliberately generic (not per-category) since the
# distinction it's naming — "the broader period, not this specific phase,
# is what connects here" — reads the same regardless of which event it is.
# Not shown for "karaka_antardasha": a karaka's OWN Antardasha is real
# classical evidence (that's why marriage_rules/event_rules score it in the
# first place), just a more generic signal than the house lord's — a
# distinction _evidence_level exposes for callers/analysis, but not one
# this app currently treats as worth a caveat sentence.
_WEAK_EVIDENCE_EN = (
    "No period whose own narrower phase is directly tied to this was found nearby — this window only "
    "qualifies through the broader multi-year period it falls in, a real but comparatively weaker signal."
)
_WEAK_EVIDENCE_HI = (
    "आस-पास ऐसी कोई अवधि नहीं मिली जिसका अपना छोटा दौर सीधे इससे जुड़ा हो — यह अवधि केवल उस बड़ी बहु-वर्षीय "
    "अवधि के कारण योग्य मानी गई है जिसके अंतर्गत यह आती है, जो एक वास्तविक पर तुलनात्मक रूप से कमज़ोर संकेत है।"
)


def _weak_evidence_sentence(evidence_level: str, hi: bool) -> str | None:
    if evidence_level != "backdrop_only":
        return None
    return _WEAK_EVIDENCE_HI if hi else _WEAK_EVIDENCE_EN

# Surfaces app.astro.event_window_scanner's Mahadasha/Antardasha relationship
# weighting (see its _DASHA_RELATIONSHIP_MULTIPLIER) as plain language.
# Shared between marriage and life-event reason text — the relationship
# between the two dasha levels means the same thing regardless of which
# event is being timed. Keyed by the exact
# "dasha_relationship_{same,friend,enemy}" reason keys scan_dasha_windows
# emits; "neutral" never appears as a reason key (silent by design there),
# so there is deliberately no entry for it here.
_DASHA_RELATIONSHIP_REASON_EN: dict[str, str] = {
    "dasha_relationship_same": "The same planet is running both the broader period and this specific phase, which classically gives an unusually focused, unmixed dose of its results.",
    "dasha_relationship_friend": "The two planets running this phase and the broader period are natural friends, so their effects tend to reinforce each other rather than pull in different directions.",
    "dasha_relationship_enemy": "The two planets running this phase and the broader period are natural enemies, so results here can come with more friction or mixed signals than the classical rule alone suggests.",
}
_DASHA_RELATIONSHIP_REASON_HI: dict[str, str] = {
    "dasha_relationship_same": "इस विशेष दौर और उसकी बड़ी अवधि, दोनों की बागडोर एक ही ग्रह के हाथ में है — इससे शास्त्रीय रूप से उस ग्रह के परिणाम असामान्य रूप से केंद्रित और स्पष्ट मिलते हैं।",
    "dasha_relationship_friend": "इस दौर और इसकी बड़ी अवधि को चलाने वाले दोनों ग्रह स्वाभाविक मित्र हैं, इसलिए उनके प्रभाव एक-दूसरे के विपरीत जाने की बजाय एक-दूसरे को मज़बूत करते हैं।",
    "dasha_relationship_enemy": "इस दौर और इसकी बड़ी अवधि को चलाने वाले दोनों ग्रह स्वाभाविक शत्रु हैं, इसलिए यहां के परिणामों में सामान्य से ज़्यादा उलझन या मिश्रित संकेत आ सकते हैं।",
}


def _dasha_relationship_sentences(reason_keys: list[str], hi: bool) -> list[str]:
    pool = _DASHA_RELATIONSHIP_REASON_HI if hi else _DASHA_RELATIONSHIP_REASON_EN
    return [pool[k] for k in reason_keys if k in pool]


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
    ("is also well-placed in your birth chart itself", "was also well-placed in your birth chart itself"),
    ("is weakly placed in your birth chart itself", "was weakly placed in your birth chart itself"),
    (
        "is running both the broader period and this specific phase, which classically gives",
        "ran both the broader period and that specific phase, which classically gave",
    ),
    (
        "their effects tend to reinforce each other rather than pull in different directions",
        "their effects tended to reinforce each other rather than pull in different directions",
    ),
    (
        "results here can come with more friction or mixed signals than the classical rule alone suggests",
        "results there came with more friction or mixed signals than the classical rule alone suggested",
    ),
    ("is also retrograde right now", "was also retrograde during that period"),
    ("what that means here", "what that meant there"),
    (
        "is also transiting through that same part of your chart",
        "was also transiting through that same part of your chart",
    ),
    ("This window falls earlier in life than", "That window fell earlier in life than"),
    ("This window falls later in life than", "That window fell later in life than"),
]
_TENSE_REPLACEMENTS_HI: list[tuple[str, str]] = [
    ("सक्रिय है", "सक्रिय था"),
    ("अंतर्गत आती है", "अंतर्गत आई थी"),
    ("गुज़र रहे हैं", "गुज़र रहे थे"),
    ("गुज़र रहा है", "गुज़रा था"),
    ("इस अवधि के दौरान", "उस अवधि के दौरान"),
    ("इस दौर में", "उस दौर में"),
    ("इसी दौरान", "उसी दौरान"),
    ("मज़बूत स्थिति में है", "मज़बूत स्थिति में था"),
    ("कमज़ोर स्थिति में है", "कमज़ोर स्थिति में था"),
    ("असामान्य रूप से केंद्रित और स्पष्ट मिलते हैं", "असामान्य रूप से केंद्रित और स्पष्ट मिले"),
    ("एक-दूसरे को मज़बूत करते हैं", "एक-दूसरे को मज़बूत करते थे"),
    ("मिश्रित संकेत आ सकते हैं", "मिश्रित संकेत आए"),
    ("फ़िलहाल वक्री (retrograde) भी है", "उस दौरान भी वक्री (retrograde) था"),
    ("यह अवधि उस सामान्य उम्र से पहले की है", "वह अवधि उस सामान्य उम्र से पहले की थी"),
    ("यह अवधि उस सामान्य उम्र के बाद की है", "वह अवधि उस सामान्य उम्र के बाद की थी"),
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
    natal_strength: NatalStrength | None = None,
    antardasha_lord_retrograde: bool = False,
    transit_obstructing_planet: str | None = None,
    age_implausibility: Literal["early", "late"] | None = None,
    literal_event_plausible: bool = True,
    evidence_level: str = "house_lord_antardasha",
) -> str:
    """Leads with a real, plain-language EFFECT (the running planet's own
    classical one-liner, already written for period_analysis — honest,
    tested, jargon-free) before the "why" mechanism explanation, instead of
    opening with Sanskrit period-names a reader has to already know.

    `natal_strength` ("strong"/"weak"/None) surfaces whether the Antardasha
    lord itself is dignified or afflicted in the natal chart — the same
    signal that already scales this window's score
    (app.astro.natal_insights.significator_strength) — as an explicit
    sentence instead of only ever affecting ranking silently.

    `antardasha_lord_retrograde` surfaces the SAME retrograde fact every
    chart already computes (app.astro.charts) but never mentions elsewhere
    in the Prediction Engine — purely informational, never scored (see
    prediction_service._significator_retrograde for why).

    `transit_obstructing_planet` (a pre-localized display name, or None) is
    the SAME obstruction signal that already scales this window's score
    downward (app.astro.transit_corroboration) — surfaced explicitly rather
    than only ever affecting ranking silently, same convention as
    `natal_strength`. Can appear alongside `transit_corroborated=True`: the
    two are independent, not contradictory (see the module comment on
    _TRANSIT_OBSTRUCTION_EN).

    `age_implausibility` ("early"/"late"/None) surfaces the SAME real-world
    (not classical) age-sanity factor that already scales this window's
    score down (app.astro.life_stage_plausibility) — explicit rather than
    silent, same convention as every factor above.

    `literal_event_plausible=False` means prediction_service could not find
    ANY plausible-age window in the search horizon (see
    app.astro.life_stage_plausibility.is_hard_implausible_age and
    prediction_service._select_candidate_pool) and is returning this one
    anyway as the best available signal — stronger than `age_implausibility`
    above, which still presents the window as a literal (if lower-
    confidence) prediction. Appends an honest reinterpretation sentence
    instead of letting the reader take the literal event at face value.

    `evidence_level` ("house_lord_antardasha" > "karaka_antardasha" >
    "backdrop_only" — see prediction_service._evidence_level) says how
    directly THIS window's own Antardasha ties to the event: the house
    lord's own Antardasha, a karaka's own Antardasha (real evidence, but a
    more generic signal), or only its broader Mahadasha (a real but
    comparatively weak signal). Only "backdrop_only" appends an honest
    note — a karaka's own Antardasha is real classical evidence, not one
    this app currently treats as worth a caveat, just a coarser one than
    the house lord's."""
    hi = language == "hi"
    pool = _MARRIAGE_REASON_HI if hi else _MARRIAGE_REASON_EN
    content_pool = _PERIOD_CONTENT_HI if hi else _PERIOD_CONTENT_EN
    names = PLANET_NAMES_HI if hi else PLANET_NAMES_EN
    effect = content_pool.get(antardasha_lord, content_pool["Mo"])["one_liner"]

    sentences = [pool[k].format(lord=seventh_lord_name) for k in reason_keys if k in pool]
    sentences.extend(_dasha_relationship_sentences(reason_keys, hi))
    mechanism = " ".join(sentences)
    if natal_strength is not None:
        strength_pool = _NATAL_STRENGTH_HI if hi else _NATAL_STRENGTH_EN
        mechanism += " " + strength_pool[natal_strength].format(name=names[antardasha_lord])
    if antardasha_lord_retrograde:
        mechanism += " " + (_RETROGRADE_NOTE_HI if hi else _RETROGRADE_NOTE_EN).format(name=names[antardasha_lord])
    if transit_corroborated:
        mechanism += " " + (_TRANSIT_CORROBORATION_HI if hi else _TRANSIT_CORROBORATION_EN)
    if transit_obstructing_planet is not None:
        template = _TRANSIT_OBSTRUCTION_HI if hi else _TRANSIT_OBSTRUCTION_EN
        mechanism += " " + template.format(planet=transit_obstructing_planet)
    age_sentence = _age_implausibility_sentence("marriage", age_implausibility, hi)
    if age_sentence is not None:
        mechanism += " " + age_sentence
    reinterpretation = _reinterpretation_sentence("marriage", literal_event_plausible, hi)
    if reinterpretation is not None:
        mechanism += " " + reinterpretation
    weak_evidence = _weak_evidence_sentence(evidence_level, hi)
    if weak_evidence is not None:
        mechanism += " " + weak_evidence
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
    natal_strength: NatalStrength | None = None,
    antardasha_lord_retrograde: bool = False,
    transit_obstructing_planet: str | None = None,
    age_implausibility: Literal["early", "late"] | None = None,
    literal_event_plausible: bool = True,
    evidence_level: str = "house_lord_antardasha",
) -> str:
    """Leads with a real, plain-language EFFECT (the running planet's own
    classical one-liner) before the "why" mechanism sentences, mirroring
    marriage_window_reason_text above — no Sanskrit period-names up front.

    `natal_strength`, `antardasha_lord_retrograde`, `transit_obstructing_
    planet`, `age_implausibility`, `literal_event_plausible`, and
    `evidence_level` mirror marriage_window_reason_text's parameters of
    the same name — see its docstring."""
    hi = language == "hi"
    house_phrase = (_EVENT_HOUSE_PHRASE_HI if hi else _EVENT_HOUSE_PHRASE_EN)[event_type]
    karaka_names = _EVENT_KARAKA_NAME_HI if hi else _EVENT_KARAKA_NAME_EN
    karaka_descs = _EVENT_KARAKA_DESC_HI if hi else _EVENT_KARAKA_DESC_EN
    content_pool = _PERIOD_CONTENT_HI if hi else _PERIOD_CONTENT_EN
    names = PLANET_NAMES_HI if hi else PLANET_NAMES_EN
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

    sentences.extend(_dasha_relationship_sentences(reason_keys, hi))
    mechanism = " ".join(sentences)
    if natal_strength is not None:
        strength_pool = _NATAL_STRENGTH_HI if hi else _NATAL_STRENGTH_EN
        mechanism += " " + strength_pool[natal_strength].format(name=names[antardasha_lord])
    if antardasha_lord_retrograde:
        mechanism += " " + (_RETROGRADE_NOTE_HI if hi else _RETROGRADE_NOTE_EN).format(name=names[antardasha_lord])
    if transit_corroborated:
        template = _EVENT_TRANSIT_CORROBORATION_HI if hi else _EVENT_TRANSIT_CORROBORATION_EN
        mechanism += " " + template.format(house=house_phrase)
    if transit_obstructing_planet is not None:
        template = _TRANSIT_OBSTRUCTION_HI if hi else _TRANSIT_OBSTRUCTION_EN
        mechanism += " " + template.format(planet=transit_obstructing_planet)
    age_sentence = _age_implausibility_sentence(event_type, age_implausibility, hi)
    if age_sentence is not None:
        mechanism += " " + age_sentence
    reinterpretation = _reinterpretation_sentence(event_type, literal_event_plausible, hi)
    if reinterpretation is not None:
        mechanism += " " + reinterpretation
    weak_evidence = _weak_evidence_sentence(evidence_level, hi)
    if weak_evidence is not None:
        mechanism += " " + weak_evidence
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
