"""Prediction Engine: year-ahead / multi-year outlook (Varshaphala + running
dasha + transit doshas) and marriage-timing prediction (dasha/transit window
scan). Every fact here is computed from the person's real birth data — no
LLM call, no scraped/templated third-party content (see the Prediction
Engine plan). Both languages are computed and cached together, same
convention as every other cached artifact in this app.
"""
from datetime import datetime, timezone

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.constants import PLANET_NAMES_EN, PLANET_NAMES_HI
from app.astro.dasha import find_current_antardasha, find_current_mahadasha
from app.astro.doshas import compute_sade_sati
from app.astro.manglik import compute_manglik_facts
from app.astro.marriage_timing import corroborate_with_transits, find_marriage_windows
from app.astro.natal_insights import house_lord, planet_dignity
from app.astro.transits import compute_transit_snapshot
from app.astro.varshaphala import compute_solar_return, compute_varshaphala
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import MarriageTimingCache, YearOutlookCache
from app.schemas.prediction import MarriageTimingResponse, MultiYearOutlookResponse, YearOutlookResponse
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_service import birth_datetime_utc, get_chart
from app.services.dasha_service import get_mahadashas_raw
from app.services.interpretation.base import Language
from app.services.interpretation.prediction_templates import (
    marriage_window_reason_text,
    overall_year_theme,
    year_outlook_text,
)

MAX_MULTI_YEARS = 3


def _year_select_stmt(profile: BirthProfile, year: int, language: Language):
    return select(YearOutlookCache).where(
        YearOutlookCache.user_id == profile.user_id,
        YearOutlookCache.year == year,
        YearOutlookCache.language == language,
        YearOutlookCache.birth_profile_version == profile.version,
    )


async def get_year_ahead(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, year: int, language: Language
) -> YearOutlookResponse:
    _REQUIRED_CACHE_KEYS = ("quarters", "varsheshwar")
    select_stmt = _year_select_stmt(profile, year, language)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if cached_row is not None and all(k in cached_row.data for k in _REQUIRED_CACHE_KEYS):
        return YearOutlookResponse(year=year, language=language, cached=True, **cached_row.data)

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    sun = next(p for p in d1.planets if p.planet == "Su")
    planet_house = {p.planet: p.house for p in d1.planets}
    planet_sign = {p.planet: p.sign_index for p in d1.planets}

    birth_dt = birth_datetime_utc(birth)
    sun_longitude = sun.sign_index * 30 + (sun.degree_in_sign or 0.0)

    def _compute_varshaphala_and_bounds():
        varshaphala = compute_varshaphala(
            birth_dt, sun_longitude, d1.lagna_sign_index, birth.latitude, birth.longitude, year
        )
        year_end = compute_solar_return(birth_dt, sun_longitude, year + 1)
        return varshaphala, year_end

    varshaphala, year_end = await anyio.to_thread.run_sync(_compute_varshaphala_and_bounds)
    year_start = varshaphala.solar_return_dt
    quarter_span = (year_end - year_start) / 4

    mahadashas = await get_mahadashas_raw(db, profile, birth)

    quarter_bounds = []
    cursor = year_start
    for i in range(4):
        q_end = cursor + quarter_span if i < 3 else year_end
        quarter_bounds.append((cursor, q_end))
        cursor = q_end
    midpoints = [q_start + (q_end - q_start) / 2 for q_start, q_end in quarter_bounds]

    def _quarter_transit_snapshots():
        return [compute_transit_snapshot(at, d1.lagna_sign_index, moon.sign_index) for at in midpoints]

    snapshots = await anyio.to_thread.run_sync(_quarter_transit_snapshots)

    varsheshwar_dignity = planet_dignity(varshaphala.varsheshwar, planet_sign[varshaphala.varsheshwar])
    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN

    quarters_out = []
    quarter_ratings = []
    for (q_start, q_end), midpoint, snapshot in zip(quarter_bounds, midpoints, snapshots):
        maha = find_current_mahadasha(mahadashas, midpoint)
        antar = find_current_antardasha(maha, midpoint) if maha is not None else None
        if maha is None or antar is None:
            # The dasha timeline (one full ~120-year Vimshottari cycle from
            # birth) should cover any realistic requested year — skip
            # gracefully rather than crash if a caller ever requests a year
            # past that horizon.
            continue

        antar_house = planet_house.get(antar.lord)
        antar_dignity = planet_dignity(antar.lord, planet_sign[antar.lord]) if antar.lord in planet_sign else "neutral"
        if antar_house is None:
            continue

        sade_sati = compute_sade_sati(moon.sign_index, snapshot.planet_sign_index["Sa"])
        dosha_notes = []
        if sade_sati.is_active:
            dosha_notes.append(
                f"शनि की साढ़े साती इस दौरान {sade_sati.phase} चरण में है।"
                if language == "hi" else
                f"Saturn's Sade Sati is in its {sade_sati.phase} phase during this stretch."
            )

        text = year_outlook_text(
            antardasha_lord=antar.lord,
            antardasha_lord_house=antar_house,
            antardasha_lord_dignity=antar_dignity,
            varsheshwar=varshaphala.varsheshwar,
            varsheshwar_dignity=varsheshwar_dignity,
            muntha_house=varshaphala.muntha_house_from_varsha_lagna,
            jupiter_transit_house_from_moon=snapshot.planet_house_from_moon["Ju"],
            saturn_transit_house_from_moon=snapshot.planet_house_from_moon["Sa"],
            active_dosha_notes=dosha_notes,
            language=language,
        )
        quarters_out.append(
            {
                # ISO strings, not date objects — the JSON cache column's
                # default encoder can't serialize a bare `date` (see
                # windows_out below in get_marriage_timing for the same
                # convention). Pydantic parses an ISO date string back into
                # a `date` field just as readily as a real `date` object, so
                # this is transparent to both the cache write and the
                # immediate (uncached) response construction below.
                "start_date": q_start.date().isoformat(),
                "end_date": q_end.date().isoformat(),
                "dominant_dasha_lord": antar.lord,
                "dominant_dasha_lord_name": names[antar.lord],
                "theme": text["theme"],
                "rating": text["rating"],
                "opportunities": text["opportunities"],
                "risks": text["risks"],
            }
        )
        quarter_ratings.append(text["rating"])

    overall_rating = round(sum(quarter_ratings) / len(quarter_ratings)) if quarter_ratings else 5
    overall_theme = overall_year_theme(
        varshaphala.varsheshwar, varsheshwar_dignity, varshaphala.muntha_house_from_varsha_lagna, language
    )

    data = {
        "overall_rating": overall_rating,
        "overall_theme": overall_theme,
        "varsheshwar": varshaphala.varsheshwar,
        "varsheshwar_name": names[varshaphala.varsheshwar],
        "muntha_house": varshaphala.muntha_house_from_varsha_lagna,
        "quarters": quarters_out,
    }

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        return YearOutlookResponse(year=year, language=language, cached=False, **data)

    row = YearOutlookCache(
        user_id=profile.user_id, year=year, language=language, birth_profile_version=profile.version, data=data
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)
    return YearOutlookResponse(year=year, language=language, cached=was_race, **data)


async def get_multi_year_outlook(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, years: int, language: Language
) -> MultiYearOutlookResponse:
    years = min(years, MAX_MULTI_YEARS)
    current_year = datetime.now(timezone.utc).year
    results = [await get_year_ahead(db, profile, birth, current_year + i, language) for i in range(years)]
    return MultiYearOutlookResponse(years=results)


def _marriage_select_stmt(profile: BirthProfile, language: Language):
    return select(MarriageTimingCache).where(
        MarriageTimingCache.user_id == profile.user_id,
        MarriageTimingCache.language == language,
        MarriageTimingCache.birth_profile_version == profile.version,
    )


async def get_marriage_timing(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, language: Language
) -> MarriageTimingResponse:
    _REQUIRED_CACHE_KEYS = ("windows",)
    select_stmt = _marriage_select_stmt(profile, language)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if cached_row is not None and all(k in cached_row.data for k in _REQUIRED_CACHE_KEYS):
        return MarriageTimingResponse(language=language, cached=True, **cached_row.data)

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    mars = next(p for p in d1.planets if p.planet == "Ma")
    mahadashas = await get_mahadashas_raw(db, profile, birth)
    seventh_lord = house_lord(7, d1.lagna_sign_index)
    now = datetime.now(timezone.utc)

    def _compute_windows():
        windows = find_marriage_windows(mahadashas, seventh_lord, now)
        return [(w, corroborate_with_transits(w, d1.lagna_sign_index, moon.sign_index)) for w in windows]

    scored_windows = await anyio.to_thread.run_sync(_compute_windows)

    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
    seventh_lord_name = names[seventh_lord]
    windows_out = []
    for w, corroborated in scored_windows:
        reason = marriage_window_reason_text(w.reason_keys, seventh_lord_name, corroborated, language)
        windows_out.append(
            {
                # ISO strings, not date objects — see the matching comment
                # in get_year_ahead above.
                "start_date": w.start.date().isoformat(),
                "end_date": w.end.date().isoformat(),
                "mahadasha_lord": w.mahadasha_lord,
                "mahadasha_lord_name": names[w.mahadasha_lord],
                "antardasha_lord": w.antardasha_lord,
                "antardasha_lord_name": names[w.antardasha_lord],
                "score": w.score,
                "reason": reason,
                "transit_corroborated": corroborated,
            }
        )

    manglik = compute_manglik_facts(
        mars_sign_index=mars.sign_index, mars_house_from_lagna=mars.house, moon_sign_index=moon.sign_index
    )
    manglik_note = None
    if manglik.is_manglik:
        manglik_note = (
            "आपकी कुंडली में मंगलिक दोष है — कई परिवार विवाह से पहले साथी की कुंडली से इसका मिलान करते हैं।"
            if language == "hi" else
            "Your chart shows Manglik (Mangal) Dosha — many families match this specifically against a "
            "partner's chart before marriage."
        )

    data = {"windows": windows_out, "manglik_note": manglik_note}

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        return MarriageTimingResponse(language=language, cached=False, **data)

    row = MarriageTimingCache(
        user_id=profile.user_id, language=language, birth_profile_version=profile.version, data=data
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)
    return MarriageTimingResponse(language=language, cached=was_race, **data)
