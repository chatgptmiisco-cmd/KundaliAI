"""Per-focus-area "how is today for this part of my life" readings — the
piece that makes a user's chosen focus areas (family/health/career/marriage/
friends, picked during onboarding) pay off with real content on Home instead
of only feeding the generic canned insights table.

Each area maps to its classical house (4th=family, 6th=health, 10th=career,
7th=marriage & relationships, 11th=friends). For that house we look at who
rules it (already computed by app.astro.natal_insights, generalized to all
12 houses this session), how that lord is placed and dignified, and whether
anything is transiting the house *today* — the same ingredients
app.services.daily_reading_service uses, just aimed at one specific house
per area instead of wherever the antardasha lord happens to sit.

Beyond the placement fact, each reading also answers "what does that
actually mean, and what should I do" by reusing the same hand-written
per-lord toolkit (_LIFE_FRAMING for the lord's general strength/challenge
nature, _PERIOD_CONTENT for a today-varying risk/opportunity pair, picked
off the real tithi index so it isn't the same line every day) that
daily_reading_service already uses for the Mahadasha/Antardasha lords —
here applied to whichever lord actually rules this specific life area.

No LLM — plain rule-based Python, same as every other service in this app.
"""
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.constants import PLANET_NAMES_EN, PLANET_NAMES_HI, PlanetKey
from app.astro.ephemeris import all_planet_positions, julian_day_ut
from app.astro.natal_insights import NatalInsights, compute_natal_insights
from app.astro.panchang import compute_tithi
from app.astro.transits import TransitSnapshot, compute_transit_snapshot
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import FocusReadingCache
from app.schemas.focus_reading import FocusReadingsResponse
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_service import get_chart
from app.services.interpretation.templates import (
    _DIGNITY_QUALIFIER_EN,
    _DIGNITY_QUALIFIER_HI,
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

FOCUS_AREA_HOUSES: dict[str, int] = {
    "family": 4,
    "health": 6,
    "career": 10,
    "marriage_relationships": 7,
    "friends": 11,
}

_BENEFIC_TRANSITS: tuple[PlanetKey, ...] = ("Ju", "Ve")
_MALEFIC_TRANSITS: tuple[PlanetKey, ...] = ("Sa", "Ma", "Ra", "Ke")
_TRANSIT_NOTE_PRIORITY: tuple[PlanetKey, ...] = ("Sa", "Ju", "Ra", "Ke", "Ma", "Ve", "Me", "Su", "Mo")
_DUSTHANA_HOUSES = {6, 8, 12}
_GROWTH_HOUSES = {1, 4, 5, 7, 9, 10, 11}


def _build_focus_readings(
    *,
    language: str,
    insights: NatalInsights,
    transit_snapshot: TransitSnapshot,
    sun_longitude_today: float,
    moon_longitude_today: float,
) -> list[dict]:
    hi = language == "hi"
    names = PLANET_NAMES_HI if hi else PLANET_NAMES_EN
    focus = _FOCUS_BY_HOUSE_HI if hi else _FOCUS_BY_HOUSE_EN
    qualifier = _DIGNITY_QUALIFIER_HI if hi else _DIGNITY_QUALIFIER_EN
    life_framing = _LIFE_FRAMING_HI if hi else _LIFE_FRAMING_EN
    period_content = _PERIOD_CONTENT_HI if hi else _PERIOD_CONTENT_EN

    tithi = compute_tithi(sun_longitude_today, moon_longitude_today)

    readings = []
    for area, house in FOCUS_AREA_HOUSES.items():
        lord = insights.house_lords[house]
        lord_house = insights.house_lord_houses[house]
        dignity = insights.planet_dignity.get(lord, "neutral")
        theme = focus[house]
        content = period_content.get(lord, period_content["Mo"])
        framing = life_framing.get(lord, life_framing["Mo"])

        rating = 6
        if dignity == "exalted":
            rating += 3
        elif dignity == "own_sign":
            rating += 2
        elif dignity == "debilitated":
            rating -= 3
        if lord_house in _DUSTHANA_HOUSES:
            rating -= 1
        elif lord_house in _GROWTH_HOUSES:
            rating += 1

        transiting_here = [p for p, h in transit_snapshot.planet_house_from_lagna.items() if h == house]
        if any(p in _BENEFIC_TRANSITS for p in transiting_here):
            rating += 1
        if any(p in _MALEFIC_TRANSITS for p in transiting_here):
            rating -= 1
        rating = max(1, min(10, rating))

        if hi:
            summary = (
                f"आपके {theme} (भाव {house}) के स्वामी {names[lord]} आपके {_hindi_house(lord_house)} में हैं और "
                f"{qualifier[dignity]}।"
            )
        else:
            summary = (
                f"Your {theme} (house {house}) is ruled by {names[lord]}, placed in your "
                f"{_ordinal(lord_house)} house — {qualifier[dignity]}."
            )

        # "What does that mean" — the lord's real, per-chart strength or
        # challenge nature when it clearly leans one way, or its general
        # tendency (reused from the period-analysis toolkit) when the
        # placement is simply neutral.
        if dignity in ("exalted", "own_sign"):
            trait = framing["core_strength"]
        elif dignity == "debilitated":
            trait = framing["core_challenge"]
        else:
            trait = content["one_liner"]
        if hi:
            meaning = f"{names[lord]} यहां {theme} को दिशा देता है — {_strip_trailing_stop(trait)}।"
        else:
            meaning = f"{names[lord]} is what actually drives your {theme} here — {_strip_trailing_stop(trait)}."

        # "What to avoid / lean into today" — reuse the same hand-written
        # risk/opportunity pool daily_reading_service uses for dasha lords,
        # picked off today's real tithi index so it varies day to day
        # instead of repeating the same line for weeks.
        risks, opportunities = content["risks"], content["opportunities"]
        risk_today = risks[tithi.index % len(risks)]
        opportunity_today = opportunities[(tithi.index + 1) % len(opportunities)]
        if hi:
            avoid_today = f"{theme} में आज ध्यान रखें: {_strip_trailing_stop(risk_today)}।"
            focus_today = f"{theme} में आज मौका: {_strip_trailing_stop(opportunity_today)}।"
        else:
            avoid_today = f"In {theme}, watch out: {_strip_trailing_stop(risk_today).lower()}."
            focus_today = f"In {theme}, the opening today: {_strip_trailing_stop(opportunity_today).lower()}."

        transit_note = None
        priority_planet = next((p for p in _TRANSIT_NOTE_PRIORITY if p in transiting_here), None)
        if priority_planet:
            # State the real consequence (which way this pushes {theme} today),
            # not just the bare fact that a planet is passing through — a
            # benefic and a malefic transit through the same house mean
            # opposite things for the day, reusing the same benefic/malefic
            # classification already driving the rating adjustment above.
            if priority_planet in _BENEFIC_TRANSITS:
                effect_en = f"a genuinely good window to make real progress on {theme} today"
                effect_hi = f"आज {theme} में वास्तविक प्रगति करने का अच्छा मौका है"
            elif priority_planet in _MALEFIC_TRANSITS:
                effect_en = f"more friction or delay than usual around {theme} — patience will serve you better than pushing"
                effect_hi = f"आज {theme} में सामान्य से ज़्यादा रुकावट या देरी हो सकती है — जल्दबाज़ी से बेहतर है धैर्य रखना"
            else:
                effect_en = f"{theme} is more active and attention-grabbing than usual today"
                effect_hi = f"आज {theme} सामान्य से ज़्यादा सक्रिय और ध्यान खींचने वाला रहेगा"
            transit_note = (
                f"{names[priority_planet]} अभी इस भाव से गुज़र रहा है — इसका मतलब है {effect_hi}।"
                if hi
                else f"{names[priority_planet]} is transiting this house right now — that means {effect_en}."
            )

        readings.append(
            {
                "area": area,
                "house": house,
                "house_lord": lord,
                "house_lord_house": lord_house,
                "dignity": dignity,
                "rating": rating,
                "theme": theme,
                "summary": summary,
                "meaning": meaning,
                "avoid_today": avoid_today,
                "focus_today": focus_today,
                "transit_note": transit_note,
            }
        )
    return readings


def _select_stmt(profile: BirthProfile, for_date: date, language: str):
    return select(FocusReadingCache).where(
        FocusReadingCache.user_id == profile.user_id,
        FocusReadingCache.reading_date == for_date,
        FocusReadingCache.language == language,
        FocusReadingCache.birth_profile_version == profile.version,
    )


async def get_focus_readings(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, for_date: date, language: str,
) -> FocusReadingsResponse:
    result = await db.execute(_select_stmt(profile, for_date, language))
    cached_row = result.scalar_one_or_none()
    if cached_row is not None:
        return FocusReadingsResponse(date=for_date, language=language, cached=True, readings=cached_row.data["readings"])

    d1 = await get_chart(db, profile, birth, "D1")
    natal_planet_sign_index = {p.planet: p.sign_index for p in d1.planets}
    natal_planet_house = {p.planet: p.house for p in d1.planets}
    moon = next(p for p in d1.planets if p.planet == "Mo")

    insights = compute_natal_insights(d1.lagna_sign_index, natal_planet_sign_index, natal_planet_house)

    at = datetime(for_date.year, for_date.month, for_date.day, 12, 0, tzinfo=timezone.utc)
    transit_snapshot = compute_transit_snapshot(at, d1.lagna_sign_index, moon.sign_index)
    today_jd_ut = julian_day_ut(at)
    today_positions = all_planet_positions(today_jd_ut)

    readings = _build_focus_readings(
        language=language,
        insights=insights,
        transit_snapshot=transit_snapshot,
        sun_longitude_today=today_positions["Su"].longitude,
        moon_longitude_today=today_positions["Mo"].longitude,
    )

    row = FocusReadingCache(
        user_id=profile.user_id, reading_date=for_date, language=language,
        birth_profile_version=profile.version, data={"readings": readings},
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, _select_stmt(profile, for_date, language))

    return FocusReadingsResponse(date=for_date, language=language, cached=was_race, readings=data["readings"])
