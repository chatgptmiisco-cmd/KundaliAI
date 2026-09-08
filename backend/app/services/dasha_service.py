"""Vimshottari dasha timeline: computed once per birth-profile version and
cached as plain JSON (datetimes as ISO strings); "is this the current
period?" is recomputed fresh on every read against wall-clock time, which is
cheap and keeps the cache valid indefinitely between birth-data edits.
"""
from datetime import datetime, timezone

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.constants import PLANET_NAMES_EN, PLANET_NAMES_HI
from app.astro.dasha import (
    Antardasha,
    Mahadasha,
    compute_mahadashas,
    compute_pratyantardashas,
    find_current_antardasha,
    find_current_mahadasha,
    find_current_sub_period,
)
from app.astro.ephemeris import julian_day_ut, planet_position
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import DashaCache
from app.schemas.dasha import (
    AntardashaOut,
    CurrentDashaResponse,
    DashaTimelineResponse,
    MahadashaOut,
    SubPeriodOut,
)
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_service import birth_datetime_utc


def _mahadashas_to_cache(mahadashas: list[Mahadasha]) -> list[dict]:
    return [
        {
            "lord": m.lord,
            "start": m.start.isoformat(),
            "end": m.end.isoformat(),
            "antardashas": [
                {"lord": a.lord, "start": a.start.isoformat(), "end": a.end.isoformat()} for a in m.antardashas
            ],
        }
        for m in mahadashas
    ]


def _cache_to_mahadashas(data: list[dict]) -> list[Mahadasha]:
    return [
        Mahadasha(
            lord=m["lord"],
            start=datetime.fromisoformat(m["start"]),
            end=datetime.fromisoformat(m["end"]),
            antardashas=[
                Antardasha(lord=a["lord"], start=datetime.fromisoformat(a["start"]), end=datetime.fromisoformat(a["end"]))
                for a in m["antardashas"]
            ],
        )
        for m in data
    ]


def _select_stmt(profile: BirthProfile):
    return select(DashaCache).where(
        DashaCache.user_id == profile.user_id, DashaCache.birth_profile_version == profile.version
    )


async def _get_or_compute_mahadashas(db: AsyncSession, profile: BirthProfile, birth: BirthDataOut) -> tuple[list[Mahadasha], bool]:
    result = await db.execute(_select_stmt(profile))
    cached_row = result.scalar_one_or_none()
    if cached_row is not None:
        return _cache_to_mahadashas(cached_row.data["mahadashas"]), True

    birth_dt = birth_datetime_utc(birth)
    jd_ut = julian_day_ut(birth_dt)
    moon_longitude = await anyio.to_thread.run_sync(lambda: planet_position(jd_ut, "Mo").longitude)
    mahadashas = await anyio.to_thread.run_sync(compute_mahadashas, birth_dt, moon_longitude, 1)

    row = DashaCache(
        user_id=profile.user_id,
        birth_profile_version=profile.version,
        data={"mahadashas": _mahadashas_to_cache(mahadashas)},
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, _select_stmt(profile))
    return _cache_to_mahadashas(data["mahadashas"]), was_race


def _mahadasha_out(m: Mahadasha, now: datetime) -> MahadashaOut:
    return MahadashaOut(
        lord=m.lord,
        lord_name_en=PLANET_NAMES_EN[m.lord],
        lord_name_hi=PLANET_NAMES_HI[m.lord],
        start=m.start,
        end=m.end,
        is_current=m.start <= now < m.end,
        antardashas=[
            AntardashaOut(
                lord=a.lord,
                lord_name_en=PLANET_NAMES_EN[a.lord],
                lord_name_hi=PLANET_NAMES_HI[a.lord],
                start=a.start,
                end=a.end,
                is_current=a.start <= now < a.end,
            )
            for a in m.antardashas
        ],
    )


async def get_mahadashas_raw(db: AsyncSession, profile: BirthProfile, birth: BirthDataOut) -> list[Mahadasha]:
    """Public wrapper around the cached computation, for callers (e.g.
    validation_service) that need the raw dataclasses rather than the API
    response shape."""
    mahadashas, _cached = await _get_or_compute_mahadashas(db, profile, birth)
    return mahadashas


async def get_dasha_timeline(db: AsyncSession, profile: BirthProfile, birth: BirthDataOut) -> DashaTimelineResponse:
    mahadashas, cached = await _get_or_compute_mahadashas(db, profile, birth)
    now = datetime.now(timezone.utc)
    return DashaTimelineResponse(mahadashas=[_mahadasha_out(m, now) for m in mahadashas], cached=cached)


async def get_current_dasha(db: AsyncSession, profile: BirthProfile, birth: BirthDataOut) -> CurrentDashaResponse | None:
    mahadashas, _cached = await _get_or_compute_mahadashas(db, profile, birth)
    now = datetime.now(timezone.utc)

    current_maha = find_current_mahadasha(mahadashas, now)
    if current_maha is None:
        return None
    current_antar = find_current_antardasha(current_maha, now)
    if current_antar is None:
        return None
    sub_periods = await anyio.to_thread.run_sync(compute_pratyantardashas, current_antar)
    current_sub = find_current_sub_period(sub_periods, now)
    if current_sub is None:
        return None

    return CurrentDashaResponse(
        mahadasha=_mahadasha_out(current_maha, now),
        antardasha=AntardashaOut(
            lord=current_antar.lord,
            lord_name_en=PLANET_NAMES_EN[current_antar.lord],
            lord_name_hi=PLANET_NAMES_HI[current_antar.lord],
            start=current_antar.start,
            end=current_antar.end,
            is_current=True,
        ),
        pratyantardasha=SubPeriodOut(
            lord=current_sub.lord,
            lord_name_en=PLANET_NAMES_EN[current_sub.lord],
            lord_name_hi=PLANET_NAMES_HI[current_sub.lord],
            start=current_sub.start,
            end=current_sub.end,
        ),
    )
