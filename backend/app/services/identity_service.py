"""Layer 1 of the Charts redesign — the "Identity Basics" hook: Big Three
(Lagna/Moon-sign/Sun-sign) with a fixed one-line meaning each, the birth
(Moon) nakshatra with its lord/symbol/meaning, and an element+modality
breakdown across Lagna + the 9 grahas.

Deliberately not DB-cached: every value here is a cheap deterministic reshape
of the already-cached D1 chart (see chart_service.get_chart) plus small
static reference tables, so there is nothing expensive to cache.
"""
from app.astro.constants import (
    ELEMENT_NAMES_EN,
    ELEMENT_NAMES_HI,
    MODALITY_NAMES_EN,
    MODALITY_NAMES_HI,
    NAKSHATRA_MEANING_EN,
    NAKSHATRA_MEANING_HI,
    NAKSHATRA_NAMES_EN,
    NAKSHATRA_SYMBOL_EN,
    NAKSHATRA_SYMBOL_HI,
    PLANET_NAMES_EN,
    PLANET_NAMES_HI,
    SIGN_ELEMENT,
    SIGN_MODALITY,
    nakshatra_lord,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.constants import PlanetKey
from app.astro.natal_insights import house_lord
from app.db.models.birth_profile import BirthProfile
from app.schemas.identity import ElementModalityPoint, IdentityResponse, NakshatraIdentity, SignIdentity
from app.schemas.user import BirthDataOut
from app.services.chart_service import get_chart
from app.services.interpretation.templates import (
    _DIGNITY_QUALIFIER_EN,
    _DIGNITY_QUALIFIER_HI,
    _FOCUS_BY_HOUSE_EN,
    _FOCUS_BY_HOUSE_HI,
    _hindi_house,
    _ordinal,
)

# Standard classical one-liners — fixed reference copy, same category as a
# glossary entry, not a per-user claim.
_LAGNA_MEANING_EN = "Your physical body, outer personality, and the path you walk through life."
_LAGNA_MEANING_HI = "आपका भौतिक शरीर, बाहरी व्यक्तित्व और जीवन में चलने वाला मार्ग।"
_MOON_MEANING_EN = "Your emotional mind — how you feel, react, and find comfort."
_MOON_MEANING_HI = "आपका भावनात्मक मन — आप कैसा महसूस करते हैं, प्रतिक्रिया देते हैं और सुकून पाते हैं।"
_SUN_MEANING_EN = "Your core identity and soul's sense of purpose."
_SUN_MEANING_HI = "आपकी मूल पहचान और आत्मा का उद्देश्य।"

_ALL_GRAHAS: list[PlanetKey] = ["Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Ra", "Ke"]


async def get_identity(db: AsyncSession, profile: BirthProfile, birth: BirthDataOut) -> IdentityResponse:
    chart = await get_chart(db, profile, birth, "D1")

    sun = next(p for p in chart.planets if p.planet == "Su")
    moon = next(p for p in chart.planets if p.planet == "Mo")

    # The real, per-chart consequence for each point: where it actually sits
    # and how well-placed it is, translated into what that means for this
    # specific user — led with, ahead of the fixed classical definition.
    lagna_lord = house_lord(1, chart.lagna_sign_index)
    lagna_lord_detail = next(p for p in chart.planets if p.planet == lagna_lord)

    def real_effect(house: int, dignity: str | None, en_frame: str, hi_frame: str) -> tuple[str, str]:
        d = dignity or "neutral"
        en = f"{en_frame} {_ordinal(house)} house, {_DIGNITY_QUALIFIER_EN[d]} — this leans your life toward {_FOCUS_BY_HOUSE_EN[house]}."
        hi = f"{hi_frame} {_hindi_house(house)} में है, {_DIGNITY_QUALIFIER_HI[d]} — यह आपके जीवन को {_FOCUS_BY_HOUSE_HI[house]} की ओर मोड़ता है।"
        return en, hi

    lagna_effect_en, lagna_effect_hi = real_effect(
        lagna_lord_detail.house, lagna_lord_detail.dignity,
        f"Your Lagna lord {PLANET_NAMES_EN[lagna_lord]} sits in your",
        f"आपके लग्न के स्वामी {PLANET_NAMES_HI[lagna_lord]} आपके",
    )
    moon_effect_en, moon_effect_hi = real_effect(
        moon.house, moon.dignity,
        "Your Moon sits in your",
        "आपका चंद्र आपके",
    )
    sun_effect_en, sun_effect_hi = real_effect(
        sun.house, sun.dignity,
        "Your Sun sits in your",
        "आपका सूर्य आपके",
    )

    lagna = SignIdentity(
        sign_en=chart.lagna_sign_name_en, sign_hi=chart.lagna_sign_name_hi,
        meaning_en=_LAGNA_MEANING_EN, meaning_hi=_LAGNA_MEANING_HI,
        real_effect_en=lagna_effect_en, real_effect_hi=lagna_effect_hi,
    )
    moon_sign = SignIdentity(
        sign_en=moon.sign_name_en, sign_hi=moon.sign_name_hi,
        meaning_en=_MOON_MEANING_EN, meaning_hi=_MOON_MEANING_HI,
        real_effect_en=moon_effect_en, real_effect_hi=moon_effect_hi,
    )
    sun_sign = SignIdentity(
        sign_en=sun.sign_name_en, sign_hi=sun.sign_name_hi,
        meaning_en=_SUN_MEANING_EN, meaning_hi=_SUN_MEANING_HI,
        real_effect_en=sun_effect_en, real_effect_hi=sun_effect_hi,
    )

    # The Moon's nakshatra name is already computed by chart_service; its
    # index is recovered by reverse lookup (names are unique and were
    # themselves derived from this same index) rather than recomputing the
    # ephemeris a second time just to get an int back.
    nak_index = NAKSHATRA_NAMES_EN.index(moon.nakshatra_name_en)
    nak_lord = nakshatra_lord(nak_index)
    nakshatra = NakshatraIdentity(
        name_en=moon.nakshatra_name_en, name_hi=moon.nakshatra_name_hi or "",
        pada=moon.nakshatra_pada or 1,
        lord_en=PLANET_NAMES_EN[nak_lord], lord_hi=PLANET_NAMES_HI[nak_lord],
        symbol_en=NAKSHATRA_SYMBOL_EN[nak_index], symbol_hi=NAKSHATRA_SYMBOL_HI[nak_index],
        meaning_en=NAKSHATRA_MEANING_EN[nak_index], meaning_hi=NAKSHATRA_MEANING_HI[nak_index],
    )

    element_modality: list[ElementModalityPoint] = [
        ElementModalityPoint(
            point_key="Lagna", point_label_en="Lagna", point_label_hi="लग्न",
            element_en=ELEMENT_NAMES_EN[SIGN_ELEMENT[chart.lagna_sign_index]],
            element_hi=ELEMENT_NAMES_HI[SIGN_ELEMENT[chart.lagna_sign_index]],
            modality_en=MODALITY_NAMES_EN[SIGN_MODALITY[chart.lagna_sign_index]],
            modality_hi=MODALITY_NAMES_HI[SIGN_MODALITY[chart.lagna_sign_index]],
        )
    ]
    for planet_key in _ALL_GRAHAS:
        p = next(pl for pl in chart.planets if pl.planet == planet_key)
        element_modality.append(
            ElementModalityPoint(
                point_key=planet_key,
                point_label_en=PLANET_NAMES_EN[planet_key], point_label_hi=PLANET_NAMES_HI[planet_key],
                element_en=ELEMENT_NAMES_EN[SIGN_ELEMENT[p.sign_index]],
                element_hi=ELEMENT_NAMES_HI[SIGN_ELEMENT[p.sign_index]],
                modality_en=MODALITY_NAMES_EN[SIGN_MODALITY[p.sign_index]],
                modality_hi=MODALITY_NAMES_HI[SIGN_MODALITY[p.sign_index]],
            )
        )

    return IdentityResponse(
        lagna=lagna, moon_sign=moon_sign, sun_sign=sun_sign,
        nakshatra=nakshatra, element_modality=element_modality,
    )
