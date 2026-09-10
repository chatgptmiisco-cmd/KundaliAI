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
from app.astro.yogas import compute_panch_mahapurusha_yogas, has_conservative_raj_yoga, has_gajakesari_yoga
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


def build_house_breakdown(chart: ChartResult) -> list[dict]:
    names_en, names_hi = PLANET_NAMES_EN, PLANET_NAMES_HI
    focus_en, focus_hi = _FOCUS_BY_HOUSE_EN, _FOCUS_BY_HOUSE_HI
    tone_en, tone_hi = _TONE_BY_LORD_EN, _TONE_BY_LORD_HI
    qualifier_en, qualifier_hi = _DIGNITY_QUALIFIER_EN, _DIGNITY_QUALIFIER_HI

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
            effect_en, effect_hi = _planet_effect(lord, lord_dignity)
            explanation_en = (
                f"No planet sits here — how {focus_en[house]} plays out depends mainly on "
                f"{names_en[lord]}, this house's lord, who sits in your {_ordinal(lord_house)} house, "
                f"{qualifier_en[lord_dignity]}. Real effect: {effect_en}"
            )
            explanation_hi = (
                f"इस भाव में कोई ग्रह नहीं है — {focus_hi[house]} का अनुभव मुख्यतः इस भाव के स्वामी "
                f"{names_hi[lord]} की स्थिति से तय होगा, जो आपके {_hindi_house(lord_house)} में है और "
                f"{qualifier_hi[lord_dignity]}। असली असर: {effect_hi}"
            )
        else:
            parts_en, parts_hi = [], []
            effects_en, effects_hi = [], []
            for p in planets_here:
                retro_en = " (retrograde)" if chart.planet_retrograde.get(p) else ""
                retro_hi = " (वक्री)" if chart.planet_retrograde.get(p) else ""
                if p in CLASSICAL_PLANETS:
                    dignity = planet_dignity(p, chart.planet_sign_index[p])
                    parts_en.append(
                        f"{names_en[p]}{retro_en} is {qualifier_en[dignity]}, bringing "
                        f"{_a_or_an(tone_en[p])} {tone_en[p]} quality"
                    )
                    parts_hi.append(f"{names_hi[p]}{retro_hi} {qualifier_hi[dignity]}, जो {tone_hi[p]} भाव लाता है")
                else:
                    dignity = None
                    parts_en.append(f"{names_en[p]}{retro_en} sits here")
                    parts_hi.append(f"{names_hi[p]}{retro_hi} यहां स्थित है")
                effect_en, effect_hi = _planet_effect(p, dignity)
                effects_en.append(f"{names_en[p]}: {effect_en}")
                effects_hi.append(f"{names_hi[p]}: {effect_hi}")

            conjunction_en = (
                f" {_join_and([names_en[p] for p in planets_here])} are conjunct here (sharing the same "
                "house), so their effects blend into one another rather than acting separately."
                if len(planets_here) > 1
                else ""
            )
            conjunction_hi = (
                f" {' और '.join(names_hi[p] for p in planets_here)} एक ही भाव में युति में हैं, इसलिए इनका असर अलग-अलग नहीं "
                "बल्कि आपस में मिला-जुला रहता है।"
                if len(planets_here) > 1
                else ""
            )
            explanation_en = (
                f"{'; '.join(parts_en)} — this house governs {focus_en[house]}, so that's where the effect lands most directly."
                f"{conjunction_en} Real effect — {' '.join(effects_en)}"
            )
            explanation_hi = (
                f"{'; '.join(parts_hi)} — यह भाव {focus_hi[house]} को दर्शाता है, इसलिए असर सीधे यहीं दिखता है।"
                f"{conjunction_hi} असली असर — {' '.join(effects_hi)}"
            )

        breakdown.append(
            {
                "house": house,
                "sign_name_en": SIGN_NAMES_EN[sign_idx],
                "sign_name_hi": SIGN_NAMES_HI[sign_idx],
                "planets": planets_here,
                "explanation_en": explanation_en,
                "explanation_hi": explanation_hi,
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
            }
        )

    dignity_map = {p: planet_dignity(p, chart.planet_sign_index[p]) for p in CLASSICAL_PLANETS}
    for m in compute_panch_mahapurusha_yogas(chart.planet_house, dignity_map):
        findings.append(
            {
                "key": f"mahapurusha_{m.planet.lower()}",
                "name_en": f"{m.name} Yoga",
                "name_hi": f"{m.name} योग",
                "description_en": _MAHAPURUSHA_DESCRIPTIONS_EN[m.planet],
                "description_hi": _MAHAPURUSHA_DESCRIPTIONS_HI[m.planet],
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
            }
        )

    return findings
