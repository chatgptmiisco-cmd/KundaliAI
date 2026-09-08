"""The "today" reading: every field a user expects from a real astrologer's
daily reading, each one traced to an actual calculation — natal chart
placements, the running Vimshottari dasha, today's transits, and today's
Panchang (tithi/weekday) — never a hardcoded message. No LLM anywhere in
this module; see app.services.interpretation for where an LLM is optionally
used (and only for prose, never for the underlying facts).

`_build_reading` is a pure function (no DB/async calls) so every field is
unit-testable against hand-constructed inputs; `get_daily_reading` is the
thin async wrapper that fetches the real chart/dasha/transit data and caches
the result per (user, date, language, birth-profile version).
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.charts import house_number
from app.astro.constants import (
    NAKSHATRA_NAMES_EN,
    NAKSHATRA_NAMES_HI,
    NAKSHATRA_SPAN_DEG,
    PLANET_NAMES_EN,
    PLANET_NAMES_HI,
    PlanetKey,
)
from app.astro.doshas import (
    CLASSICAL_PLANETS,
    compute_kaal_sarp_dosha,
    compute_kemadruma_dosha,
    compute_sade_sati,
)
from app.astro.ephemeris import all_planet_positions, julian_day_ut
from app.astro.guna_milan import _DEVA, _MANUSHYA  # reuse the Gana classification, not rebuilt
from app.astro.manglik import compute_manglik_facts
from app.astro.natal_insights import NatalInsights, compute_natal_insights
from app.astro.panchang import (
    WEEKDAY_COLOR_EN,
    WEEKDAY_COLOR_HI,
    Tithi,
    compute_tithi,
    festival_today,
    is_makar_sankranti,
    lunar_month_index,
    lunar_month_name,
    tithi_name,
    weekday_lord,
)
from app.astro.transits import TransitSnapshot, compute_transit_snapshot
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import DailyReadingCache
from app.schemas.daily_reading import DailyReadingResponse, DoshaSummaryItem
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_service import birth_datetime_utc, get_chart
from app.services.dasha_service import get_current_dasha
from app.services.interpretation.templates import (
    _FOCUS_BY_HOUSE_EN,
    _FOCUS_BY_HOUSE_HI,
    _LIFE_FRAMING_EN,
    _LIFE_FRAMING_HI,
    _PERIOD_CONTENT_EN,
    _PERIOD_CONTENT_HI,
    _hindi_house,
    _ordinal,
    _strip_trailing_stop,
)

_DUSTHANA_HOUSES = {6, 8, 12}
_GROWTH_HOUSES = {1, 4, 5, 7, 9, 10, 11}

_LORD_ENERGY_MODE: dict[PlanetKey, str] = {
    "Su": "strategic", "Mo": "rest", "Ma": "conflict_prone", "Me": "strategic",
    "Ju": "creative", "Ve": "creative", "Sa": "grind", "Ra": "conflict_prone", "Ke": "rest",
}

_TITHI_ADJECTIVE_EN = {
    "start": "a fresh-start", "consolidate": "a consolidating", "effort": "an effort-heavy",
    "avoid_starts": "a pause-and-wait", "finish": "a finishing",
}
_TITHI_ADJECTIVE_HI = {
    "start": "एक नई शुरुआत वाली", "consolidate": "स्थिर करने वाली", "effort": "मेहनत मांगने वाली",
    "avoid_starts": "रुककर इंतज़ार करने वाली", "finish": "पूरा करने वाली",
}

_DECISION_STYLE_EN = {
    "fast_and_decisive": "You decide fast and commit — a real strength, risky only when you skip the pause to check the details.",
    "steady_and_persistent": "You decide slowly and stick with it once you do — reliable, but you can miss a fast-closing window.",
    "adaptive_and_scattered": "You adapt on the fly rather than plan ahead — flexible, but consistency takes deliberate effort.",
    "impulsive_and_reactive": "You decide in the heat of the moment — the instinct is fast, but the follow-through needs a forced pause.",
}
_DECISION_STYLE_HI = {
    "fast_and_decisive": "आप तेज़ी से फैसला करते हैं और उस पर टिके रहते हैं — असली ताकत है, बस जल्दबाज़ी में बारीकियां न छोड़ें।",
    "steady_and_persistent": "आप धीरे फैसला करते हैं पर एक बार करने के बाद टिके रहते हैं — भरोसेमंद, पर तेज़ी से बंद होने वाला मौका छूट सकता है।",
    "adaptive_and_scattered": "आप पहले से योजना बनाने के बजाय मौके पर ढल जाते हैं — लचीला, पर निरंतरता के लिए जान-बूझकर मेहनत चाहिए।",
    "impulsive_and_reactive": "आप जोश के पल में फैसला लेते हैं — प्रवृत्ति तेज़ है, पर पूरा करने के लिए ज़बरदस्ती एक ठहराव चाहिए।",
}

_MOOD_BY_GANA_EN = {
    "deva": "calm and idealistic", "manushya": "practical and driven", "rakshasa": "intense and strong-willed",
}
_MOOD_BY_GANA_HI = {
    "deva": "शांत और आदर्शवादी", "manushya": "व्यावहारिक और मेहनती", "rakshasa": "तीव्र और दृढ़-इच्छाशक्ति वाला",
}

_DOSHA_LABELS_EN = {
    "manglik": "Manglik (Mangal Dosha)", "kaal_sarp": "Kaal Sarp Dosha",
    "sade_sati": "Sade Sati", "kemadruma": "Kemadruma Dosha",
}
_DOSHA_LABELS_HI = {
    "manglik": "मंगलिक (मंगल दोष)", "kaal_sarp": "कालसर्प दोष",
    "sade_sati": "साढ़े साती", "kemadruma": "केमद्रुम दोष",
}


def _gana(nakshatra_index: int) -> str:
    if nakshatra_index in _DEVA:
        return "deva"
    if nakshatra_index in _MANUSHYA:
        return "manushya"
    return "rakshasa"


def _period_type(period_rating: int, maha_key: PlanetKey, antar_key: PlanetKey) -> str:
    if maha_key in ("Ra", "Ke") or antar_key in ("Ra", "Ke"):
        return "instability"
    if period_rating >= 8:
        return "growth"
    if period_rating >= 6:
        return "consolidation"
    if period_rating >= 4:
        return "testing"
    return "grind"


def _pick_transit_highlight_planet(house_from_lagna: dict[PlanetKey, int]) -> PlanetKey:
    priority: tuple[PlanetKey, ...] = ("Sa", "Ju", "Ra", "Ke")
    notable_houses = _DUSTHANA_HOUSES | {1, 7, 10}
    for planet in priority:
        if house_from_lagna.get(planet) in notable_houses:
            return planet
    return "Sa"


def _build_reading(
    *,
    for_date: date,
    language: str,
    lagna_sign_index: int,
    moon_sign_index: int,
    rahu_sign_index: int,
    ketu_sign_index: int,
    mars_sign_index: int,
    mars_house_from_lagna: int,
    natal_planet_sign_index: dict[PlanetKey, int],
    natal_planet_house: dict[PlanetKey, int],
    natal_moon_longitude: float,
    insights: NatalInsights,
    mahadasha_lord: PlanetKey,
    antardasha_lord: PlanetKey,
    transit_snapshot: TransitSnapshot,
    sun_longitude_today: float,
    moon_longitude_today: float,
    sun_longitude_yesterday: float,
) -> dict:
    hi = language == "hi"
    names = PLANET_NAMES_HI if hi else PLANET_NAMES_EN
    focus = _FOCUS_BY_HOUSE_HI if hi else _FOCUS_BY_HOUSE_EN
    period_content = _PERIOD_CONTENT_HI if hi else _PERIOD_CONTENT_EN
    life_framing = _LIFE_FRAMING_HI if hi else _LIFE_FRAMING_EN
    tithi_adjective = _TITHI_ADJECTIVE_HI if hi else _TITHI_ADJECTIVE_EN
    decision_style_text = _DECISION_STYLE_HI if hi else _DECISION_STYLE_EN
    mood_by_gana = _MOOD_BY_GANA_HI if hi else _MOOD_BY_GANA_EN
    dosha_labels = _DOSHA_LABELS_HI if hi else _DOSHA_LABELS_EN
    weekday_color = WEEKDAY_COLOR_HI if hi else WEEKDAY_COLOR_EN
    nakshatra_names = NAKSHATRA_NAMES_HI if hi else NAKSHATRA_NAMES_EN

    tithi: Tithi = compute_tithi(sun_longitude_today, moon_longitude_today)
    moon_transit_house = transit_snapshot.planet_house_from_lagna["Mo"]

    antar_content = period_content.get(antardasha_lord, period_content["Mo"])
    maha_content = period_content.get(mahadasha_lord, period_content["Mo"])

    # --- today's rating -----------------------------------------------
    rating = antar_content["rating"]
    if moon_transit_house in _GROWTH_HOUSES:
        rating += 1
    elif moon_transit_house in _DUSTHANA_HOUSES:
        rating -= 1
    if tithi.group in ("jaya", "purna"):
        rating += 1
    elif tithi.group == "rikta":
        rating -= 1
    rating = max(1, min(10, rating))

    if hi:
        rating_reason = (
            f"{names[antardasha_lord]} अंतर्दशा की पृष्ठभूमि में आज चंद्रमा आपके "
            f"{_hindi_house(moon_transit_house)} से गुज़र रहा है, और आज {tithi_adjective[tithi.energy_tag]} तिथि है।"
        )
    else:
        rating_reason = (
            f"Running {names[antardasha_lord]} Antardasha, with today's Moon transiting your "
            f"{_ordinal(moon_transit_house)} house on {tithi_adjective[tithi.energy_tag]} tithi."
        )

    dominant_theme = focus[moon_transit_house]

    # --- energy mode -----------------------------------------------------
    if moon_transit_house in _DUSTHANA_HOUSES:
        energy_mode = "conflict_prone"
    elif tithi.group == "rikta":
        energy_mode = "grind"
    else:
        energy_mode = _LORD_ENERGY_MODE.get(antardasha_lord, "strategic")

    # --- risk / opportunity: reuse the hand-written per-lord copy, picking
    # a daily-varying entry off the tithi index so it isn't the same line
    # every day of a multi-year Antardasha ------------------------------
    risks, opportunities = antar_content["risks"], antar_content["opportunities"]
    key_risk = risks[tithi.index % len(risks)]
    key_opportunity = opportunities[(tithi.index + 1) % len(opportunities)]

    if hi:
        brutal_truth = (
            f"आज का रुख {dominant_theme} के इर्द-गिर्द है — असली जोखिम है "
            f"{_strip_trailing_stop(key_risk).lower()}, असली मौका है {_strip_trailing_stop(key_opportunity).lower()}।"
        )
    else:
        brutal_truth = (
            f"Today leans toward {dominant_theme} — the real risk is "
            f"{_strip_trailing_stop(key_risk).lower()}, the real opening is {_strip_trailing_stop(key_opportunity).lower()}."
        )

    # --- current period ----------------------------------------------
    if hi:
        mahadasha_label = f"{names[mahadasha_lord]} महादशा / {names[antardasha_lord]} अंतर्दशा"
    else:
        mahadasha_label = f"{names[mahadasha_lord]} Mahadasha / {names[antardasha_lord]} Antardasha"

    period_rating = round((maha_content["rating"] + 2 * antar_content["rating"]) / 3)
    period_type = _period_type(period_rating, mahadasha_lord, antardasha_lord)
    dominant_life_area = focus[natal_planet_house.get(antardasha_lord, 1)]

    # --- natal strength/weakness (A4) ----------------------------------
    strength_key = insights.strongest_planet or mahadasha_lord
    core_strength = life_framing.get(strength_key, life_framing["Mo"])["core_strength"]
    core_weakness = life_framing.get(insights.blind_spot_planet, life_framing["Mo"])["core_challenge"]

    if hi:
        stress_pattern = (
            f"दबाव में सबसे पहले आपका {_hindi_house(insights.stress_house)} (स्वामी {names[insights.stress_planet]}) "
            f"असर दिखाता है — {focus[insights.stress_house]} में तनाव देखें।"
        )
    else:
        stress_pattern = (
            f"Under real pressure, your {_ordinal(insights.stress_house)} house "
            f"(ruled by {names[insights.stress_planet]}) tends to give first — watch for strain around "
            f"{focus[insights.stress_house]}."
        )

    decision_style = decision_style_text[insights.decision_style]

    # --- Moon nakshatra + mood -----------------------------------------
    nakshatra_index = int((natal_moon_longitude % 360) // NAKSHATRA_SPAN_DEG)
    moon_nakshatra = nakshatra_names[nakshatra_index]
    moon_mood_tag = mood_by_gana[_gana(nakshatra_index)]

    # --- transit highlight -----------------------------------------------
    highlight_planet = _pick_transit_highlight_planet(transit_snapshot.planet_house_from_lagna)
    highlight_house = transit_snapshot.planet_house_from_lagna[highlight_planet]
    retro_note_en = " (retrograde, so its effect turns more inward)" if transit_snapshot.planet_retrograde.get(highlight_planet) else ""
    retro_note_hi = " (वक्री, इसलिए असर अधिक आंतरिक रहेगा)" if transit_snapshot.planet_retrograde.get(highlight_planet) else ""
    if hi:
        transit_highlight = (
            f"{names[highlight_planet]} अभी आपके {_hindi_house(highlight_house)} से गुज़र रहा है{retro_note_hi} — "
            f"आज {focus[highlight_house]} पर इसका असली प्रभाव है।"
        )
    else:
        transit_highlight = (
            f"{names[highlight_planet]} is transiting your {_ordinal(highlight_house)} house right now"
            f"{retro_note_en} — {focus[highlight_house]} is under real influence today."
        )

    # --- before you leave home ------------------------------------------
    accident_risk = "elevated" if transit_snapshot.planet_house_from_lagna.get("Ma") in _DUSTHANA_HOUSES else "normal"
    conflict_risk = "elevated" if energy_mode == "conflict_prone" else "normal"
    if hi:
        accident_risk_hi = "बढ़ा हुआ" if accident_risk == "elevated" else "सामान्य"
        conflict_risk_hi = "बढ़ा हुआ" if conflict_risk == "elevated" else "सामान्य"
        before_you_leave_home = [
            f"दुर्घटना/चूक का जोखिम आज: {accident_risk_hi}।",
            f"टकराव का जोखिम आज: {conflict_risk_hi}।",
            f"संभावित मानसिक स्थिति: {moon_mood_tag}।",
            f"बाहर के समय का सबसे अच्छा उपयोग: {dominant_theme}।",
            f"एक-पंक्ति की सलाह: {_strip_trailing_stop(key_risk)} — निकलने से पहले इसे ध्यान में रखें।",
        ]
    else:
        before_you_leave_home = [
            f"Accident/mishap risk today: {accident_risk}.",
            f"Conflict risk today: {conflict_risk}.",
            f"Likely mental state: {moon_mood_tag}.",
            f"Best use of time outside today: {dominant_theme}.",
            f"One-line exit advice: {_strip_trailing_stop(key_risk)} — plan around it before you leave.",
        ]

    # --- life growth task (9th house lord) ------------------------------
    ninth_lord = insights.house_lords[9]
    ninth_lord_house = insights.house_lord_houses[9]
    if hi:
        life_growth_task = (
            f"आपकी दीर्घकालिक विकास यात्रा {focus[ninth_lord_house]} में है — आपके नवम भाव के स्वामी "
            f"({names[ninth_lord]}) फिलहाल {_hindi_house(ninth_lord_house)} में हैं।"
        )
    else:
        life_growth_task = (
            f"Your long-term growth work lives in {focus[ninth_lord_house]} — your 9th-house lord "
            f"({names[ninth_lord]}) currently sits in your {_ordinal(ninth_lord_house)} house."
        )

    today_color = weekday_color[weekday_lord(for_date)]

    # --- doshas (Manglik + Kaal Sarp + Sade Sati + Kemadruma) -----------
    manglik = compute_manglik_facts(
        mars_sign_index=mars_sign_index, mars_house_from_lagna=mars_house_from_lagna, moon_sign_index=moon_sign_index,
    )
    kaal_sarp = compute_kaal_sarp_dosha(
        lagna_sign_index=lagna_sign_index, rahu_sign_index=rahu_sign_index, ketu_sign_index=ketu_sign_index,
        planet_sign_index={p: natal_planet_sign_index[p] for p in CLASSICAL_PLANETS if p in natal_planet_sign_index},
    )
    sade_sati = compute_sade_sati(
        natal_moon_sign_index=moon_sign_index,
        transiting_saturn_sign_index=transit_snapshot.planet_sign_index["Sa"],
    )
    kemadruma = compute_kemadruma_dosha(
        planet_house_from_moon={
            p: house_number(natal_planet_sign_index[p], moon_sign_index)
            for p in CLASSICAL_PLANETS if p != "Mo" and p in natal_planet_sign_index
        }
    )
    sade_sati_label = dosha_labels["sade_sati"]
    if sade_sati.is_active and sade_sati.phase:
        phase_label_hi = {"rising": "आरंभिक", "peak": "चरम", "setting": "अंतिम"}[sade_sati.phase]
        sade_sati_label = f"{sade_sati_label} ({phase_label_hi if hi else sade_sati.phase})"

    doshas = [
        DoshaSummaryItem(key="manglik", label=dosha_labels["manglik"], is_present=manglik.is_manglik),
        DoshaSummaryItem(key="kaal_sarp", label=dosha_labels["kaal_sarp"], is_present=kaal_sarp.is_present),
        DoshaSummaryItem(key="sade_sati", label=sade_sati_label, is_present=sade_sati.is_active),
        DoshaSummaryItem(key="kemadruma", label=dosha_labels["kemadruma"], is_present=kemadruma.is_present),
    ]

    return {
        "rating": rating,
        "rating_reason": rating_reason,
        "dominant_theme": dominant_theme,
        "energy_mode": energy_mode,
        "key_risk": key_risk,
        "key_opportunity": key_opportunity,
        "brutal_truth": brutal_truth,
        "mahadasha_label": mahadasha_label,
        "period_rating": period_rating,
        "period_type": period_type,
        "dominant_life_area": dominant_life_area,
        "core_strength": core_strength,
        "core_weakness": core_weakness,
        "stress_pattern": stress_pattern,
        "decision_style": decision_style,
        "moon_nakshatra": moon_nakshatra,
        "moon_mood_tag": moon_mood_tag,
        "transit_highlight": transit_highlight,
        "before_you_leave_home": before_you_leave_home,
        "life_growth_task": life_growth_task,
        "tithi_tag": tithi.energy_tag,
        "tithi_name": tithi_name(tithi, language),
        "paksha": tithi.paksha,
        "lunar_month": lunar_month_name(sun_longitude_today, language),
        "festival": (
            festival_today(lunar_month_index(sun_longitude_today), tithi, language)
            or (
                ("मकर संक्रांति" if hi else "Makar Sankranti")
                if is_makar_sankranti(sun_longitude_today, sun_longitude_yesterday)
                else None
            )
        ),
        "today_color": today_color,
        "doshas": [d.model_dump() for d in doshas],
    }


def _select_stmt(profile: BirthProfile, for_date: date, language: str):
    return select(DailyReadingCache).where(
        DailyReadingCache.user_id == profile.user_id,
        DailyReadingCache.reading_date == for_date,
        DailyReadingCache.language == language,
        DailyReadingCache.birth_profile_version == profile.version,
    )


async def get_daily_reading(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, for_date: date, language: str,
) -> DailyReadingResponse:
    _PANCHANG_KEYS = ("tithi_name", "paksha", "lunar_month", "festival")

    result = await db.execute(_select_stmt(profile, for_date, language))
    cached_row = result.scalar_one_or_none()
    if cached_row is not None and all(key in cached_row.data for key in _PANCHANG_KEYS):
        return DailyReadingResponse(date=for_date, language=language, cached=True, **cached_row.data)

    d1 = await get_chart(db, profile, birth, "D1")
    natal_planet_sign_index = {p.planet: p.sign_index for p in d1.planets}
    natal_planet_house = {p.planet: p.house for p in d1.planets}
    mars = next(p for p in d1.planets if p.planet == "Ma")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    rahu = next(p for p in d1.planets if p.planet == "Ra")
    ketu = next(p for p in d1.planets if p.planet == "Ke")

    birth_jd_ut = julian_day_ut(birth_datetime_utc(birth))
    birth_positions = all_planet_positions(birth_jd_ut)
    natal_planet_longitude = {planet: pos.longitude for planet, pos in birth_positions.items()}

    insights = compute_natal_insights(
        d1.lagna_sign_index, natal_planet_sign_index, natal_planet_house, natal_planet_longitude,
    )

    current_dasha = await get_current_dasha(db, profile, birth)
    mahadasha_lord = current_dasha.mahadasha.lord if current_dasha else "Mo"
    antardasha_lord = current_dasha.antardasha.lord if current_dasha else "Mo"

    at = datetime(for_date.year, for_date.month, for_date.day, 12, 0, tzinfo=timezone.utc)
    transit_snapshot = compute_transit_snapshot(at, d1.lagna_sign_index, moon.sign_index)
    today_jd_ut = julian_day_ut(at)
    today_positions = all_planet_positions(today_jd_ut)
    yesterday_jd_ut = julian_day_ut(at - timedelta(days=1))
    sun_longitude_yesterday = all_planet_positions(yesterday_jd_ut)["Su"].longitude

    data = _build_reading(
        for_date=for_date,
        language=language,
        lagna_sign_index=d1.lagna_sign_index,
        moon_sign_index=moon.sign_index,
        rahu_sign_index=rahu.sign_index,
        ketu_sign_index=ketu.sign_index,
        mars_sign_index=mars.sign_index,
        mars_house_from_lagna=mars.house,
        natal_planet_sign_index=natal_planet_sign_index,
        natal_planet_house=natal_planet_house,
        natal_moon_longitude=natal_planet_longitude["Mo"],
        insights=insights,
        mahadasha_lord=mahadasha_lord,
        antardasha_lord=antardasha_lord,
        transit_snapshot=transit_snapshot,
        sun_longitude_today=today_positions["Su"].longitude,
        moon_longitude_today=today_positions["Mo"].longitude,
        sun_longitude_yesterday=sun_longitude_yesterday,
    )

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        return DailyReadingResponse(date=for_date, language=language, cached=False, **data)

    row = DailyReadingCache(
        user_id=profile.user_id, reading_date=for_date, language=language,
        birth_profile_version=profile.version, data=data,
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, _select_stmt(profile, for_date, language))

    return DailyReadingResponse(date=for_date, language=language, cached=was_race, **data)
