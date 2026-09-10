"""Prediction Engine: year-ahead / multi-year outlook (Varshaphala + running
dasha + transit doshas) and marriage-timing prediction (dasha/transit window
scan). Every fact here is computed from the person's real birth data — no
LLM call, no scraped/templated third-party content (see the Prediction
Engine plan). Both languages are computed and cached together, same
convention as every other cached artifact in this app.
"""
from datetime import date, datetime, timezone
from typing import Literal

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.constants import DAYS_PER_YEAR, PLANET_NAMES_EN, PLANET_NAMES_HI
from app.astro.dasha import find_current_antardasha, find_current_mahadasha
from app.astro.doshas import compute_dhaiya, compute_sade_sati
from app.astro.event_window_scanner import ScoredWindow
from app.astro.life_event_timing import EventType
from app.astro.life_event_timing import EVENT_HOUSE as LIFE_EVENT_HOUSE
from app.astro.life_event_timing import corroborate_with_transits as corroborate_life_event_with_transits
from app.astro.life_event_timing import find_event_windows
from app.astro.manglik import compute_manglik_facts
from app.astro.marriage_timing import corroborate_with_transits, find_marriage_windows
from app.astro.natal_insights import house_lord, planet_dignity
from app.astro.transits import compute_transit_snapshot
from app.astro.varshaphala import compute_solar_return, compute_varshaphala
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import LifeEventTimingCache, LifeThemeCache, MarriageTimingCache, YearOutlookCache
from app.schemas.prediction import (
    LifeEventTimingResponse,
    LifeThemeResponse,
    MarriageTimingResponse,
    MultiYearOutlookResponse,
    YearOutlookResponse,
)
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_service import birth_datetime_utc, get_chart
from app.services.dasha_service import get_mahadashas_raw
from app.services.interpretation.base import Language
from app.services.interpretation.prediction_templates import (
    life_event_reason_text,
    life_theme_text,
    marriage_window_reason_text,
    overall_year_theme,
    year_outlook_text,
)

Direction = Literal["past", "future"]
_FUTURE_HORIZON_YEARS = 20.0


def _search_bounds(direction: Direction, birth_dt: datetime, now: datetime) -> tuple[datetime, float]:
    """Where to point the window scanner — the entire past (birth to now)
    or the usual forward-looking horizon (now to +20 years). Same scanner
    (app.astro.event_window_scanner.scan_dasha_windows) either way; this is
    purely a different choice of bounds, not new astro logic."""
    if direction == "past":
        age_years = (now - birth_dt).days / DAYS_PER_YEAR
        return birth_dt, max(age_years, 0.0)
    return now, _FUTURE_HORIZON_YEARS

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


def _marriage_select_stmt(profile: BirthProfile, direction: Direction, language: Language):
    return select(MarriageTimingCache).where(
        MarriageTimingCache.user_id == profile.user_id,
        MarriageTimingCache.direction == direction,
        MarriageTimingCache.language == language,
        MarriageTimingCache.birth_profile_version == profile.version,
    )


async def get_marriage_timing(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, language: Language, direction: Direction = "future"
) -> MarriageTimingResponse:
    _REQUIRED_CACHE_KEYS = ("windows",)
    select_stmt = _marriage_select_stmt(profile, direction, language)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if cached_row is not None and all(k in cached_row.data for k in _REQUIRED_CACHE_KEYS):
        return MarriageTimingResponse(language=language, direction=direction, cached=True, **cached_row.data)

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    mars = next(p for p in d1.planets if p.planet == "Ma")
    mahadashas = await get_mahadashas_raw(db, profile, birth)
    seventh_lord = house_lord(7, d1.lagna_sign_index)
    birth_dt = birth_datetime_utc(birth)
    now = datetime.now(timezone.utc)
    from_dt, horizon_years = _search_bounds(direction, birth_dt, now)

    def _compute_windows():
        windows = find_marriage_windows(mahadashas, seventh_lord, from_dt, horizon_years)
        return [(w, corroborate_with_transits(w, d1.lagna_sign_index, moon.sign_index)) for w in windows]

    scored_windows = await anyio.to_thread.run_sync(_compute_windows)

    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
    seventh_lord_name = names[seventh_lord]
    windows_out = []
    for w, corroborated in scored_windows:
        reason = marriage_window_reason_text(
            w.reason_keys, seventh_lord_name, w.antardasha_lord, corroborated, language, tense=direction
        )
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
        return MarriageTimingResponse(language=language, direction=direction, cached=False, **data)

    row = MarriageTimingCache(
        user_id=profile.user_id, direction=direction, language=language, birth_profile_version=profile.version,
        data=data,
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)
    return MarriageTimingResponse(language=language, direction=direction, cached=was_race, **data)


def _life_event_select_stmt(profile: BirthProfile, event_type: EventType, direction: Direction, language: Language):
    return select(LifeEventTimingCache).where(
        LifeEventTimingCache.user_id == profile.user_id,
        LifeEventTimingCache.event_type == event_type,
        LifeEventTimingCache.direction == direction,
        LifeEventTimingCache.language == language,
        LifeEventTimingCache.birth_profile_version == profile.version,
    )


async def get_life_event_timing(
    db: AsyncSession,
    profile: BirthProfile,
    birth: BirthDataOut,
    event_type: EventType,
    language: Language,
    direction: Direction = "future",
) -> LifeEventTimingResponse:
    """Career/wealth/children/foreign-travel timing — the generic sibling of
    get_marriage_timing above, built on the same window scanner via
    app.astro.life_event_timing instead of app.astro.marriage_timing."""
    _REQUIRED_CACHE_KEYS = ("windows",)
    select_stmt = _life_event_select_stmt(profile, event_type, direction, language)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if cached_row is not None and all(k in cached_row.data for k in _REQUIRED_CACHE_KEYS):
        return LifeEventTimingResponse(
            event_type=event_type, language=language, direction=direction, cached=True, **cached_row.data
        )

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    mahadashas = await get_mahadashas_raw(db, profile, birth)
    house_lord_planet = house_lord(LIFE_EVENT_HOUSE[event_type], d1.lagna_sign_index)
    birth_dt = birth_datetime_utc(birth)
    now = datetime.now(timezone.utc)
    from_dt, horizon_years = _search_bounds(direction, birth_dt, now)

    def _compute_windows() -> list[tuple[ScoredWindow, bool]]:
        windows = find_event_windows(mahadashas, event_type, house_lord_planet, from_dt, horizon_years)
        return [
            (w, corroborate_life_event_with_transits(event_type, w, d1.lagna_sign_index, moon.sign_index))
            for w in windows
        ]

    scored_windows = await anyio.to_thread.run_sync(_compute_windows)

    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
    house_lord_name = names[house_lord_planet]
    windows_out = []
    for w, corroborated in scored_windows:
        reason = life_event_reason_text(
            event_type, w.reason_keys, house_lord_name, w.antardasha_lord, corroborated, language, tense=direction
        )
        windows_out.append(
            {
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

    data = {"windows": windows_out}

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        return LifeEventTimingResponse(
            event_type=event_type, language=language, direction=direction, cached=False, **data
        )

    row = LifeEventTimingCache(
        user_id=profile.user_id,
        event_type=event_type,
        direction=direction,
        language=language,
        birth_profile_version=profile.version,
        data=data,
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)
    return LifeEventTimingResponse(
        event_type=event_type, language=language, direction=direction, cached=was_race, **data
    )


def _life_theme_select_stmt(profile: BirthProfile, target_date: date, language: Language):
    return select(LifeThemeCache).where(
        LifeThemeCache.user_id == profile.user_id,
        LifeThemeCache.target_date == target_date,
        LifeThemeCache.language == language,
        LifeThemeCache.birth_profile_version == profile.version,
    )


async def get_life_theme(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, target_date: date, language: Language
) -> LifeThemeResponse:
    """The general "what was going on then" reflection for ANY date (almost
    always past, but nothing stops asking about today or a future date too)
    — not tied to one life-event type. Reuses find_current_mahadasha/
    antardasha and compute_transit_snapshot exactly as every other feature
    in this app does, just pointed at an arbitrary target date instead of
    "now"; the only genuinely new computation is Sade Sati/Dhaiya at that
    date, both already-existing dosha checks (compute_sade_sati,
    compute_dhaiya) given a transit snapshot for any date."""
    _REQUIRED_CACHE_KEYS = ("mahadasha_lord", "theme")
    select_stmt = _life_theme_select_stmt(profile, target_date, language)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if cached_row is not None and all(k in cached_row.data for k in _REQUIRED_CACHE_KEYS):
        return LifeThemeResponse(target_date=target_date, language=language, cached=True, **cached_row.data)

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    mahadashas = await get_mahadashas_raw(db, profile, birth)
    at = datetime(target_date.year, target_date.month, target_date.day, 12, 0, tzinfo=timezone.utc)

    def _compute():
        maha = find_current_mahadasha(mahadashas, at)
        antar = find_current_antardasha(maha, at) if maha is not None else None
        snapshot = compute_transit_snapshot(at, d1.lagna_sign_index, moon.sign_index)
        return maha, antar, snapshot

    mahadasha_at, antardasha_at, snapshot = await anyio.to_thread.run_sync(_compute)

    if mahadasha_at is None or antardasha_at is None:
        # Outside the single ~120-year Vimshottari cycle this app computes
        # from birth — realistically only reachable for a target_date far
        # beyond a human lifespan. Nothing real to report.
        raise ValueError("target_date is outside the computable Dasha timeline for this chart")

    sade_sati = compute_sade_sati(moon.sign_index, snapshot.planet_sign_index["Sa"])
    dhaiya = compute_dhaiya(moon.sign_index, snapshot.planet_sign_index["Sa"])

    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
    generated = life_theme_text(
        mahadasha_lord=mahadasha_at.lord,
        antardasha_lord=antardasha_at.lord,
        sade_sati_active=sade_sati.is_active,
        dhaiya_active=dhaiya.is_active,
        language=language,
    )

    data = {
        "mahadasha_lord": mahadasha_at.lord,
        "mahadasha_lord_name": names[mahadasha_at.lord],
        "antardasha_lord": antardasha_at.lord,
        "antardasha_lord_name": names[antardasha_at.lord],
        "sade_sati_active": sade_sati.is_active,
        "dhaiya_active": dhaiya.is_active,
        "rating": generated["rating"],
        "theme": generated["theme"],
    }

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        return LifeThemeResponse(target_date=target_date, language=language, cached=False, **data)

    row = LifeThemeCache(
        user_id=profile.user_id, target_date=target_date, language=language,
        birth_profile_version=profile.version, data=data,
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)
    return LifeThemeResponse(target_date=target_date, language=language, cached=was_race, **data)
