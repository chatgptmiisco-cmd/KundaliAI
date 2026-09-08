"""Shared helper for the check-then-insert caching pattern used across
chart/dasha/manglik/kundali/horoscope/analysis services.

Under concurrent requests for the same (user, ..., version) cache key — which
genuinely happens, e.g. the frontend fires several fetches in parallel right
after onboarding — two requests can both see "not cached yet" before either
commits, then both try to insert the same unique-constrained row.

Two layers of protection:
  1. Against SQLite specifically: aiosqlite only tolerates one writer at a
     time, and under real concurrency raises "database is locked" (or worse,
     corrupts session/connection state) rather than queuing gracefully — a
     dev-only limitation Postgres doesn't have (it handles concurrent
     writers natively via MVCC). So on SQLite, every write here is
     serialized through one process-wide lock. Cheap and correct at this
     app's scale; skipped entirely on Postgres, which needs none of it.
  2. Regardless of database: if a concurrent request still manages to insert
     the same unique-constrained row first (two requests serialized by the
     lock, one after another, but the first already committed), catch the
     IntegrityError and return what the other request just wrote instead of
     crashing — same effect as if this request had been a cache hit.

The failed insert is recovered via a SAVEPOINT (`db.begin_nested()`), not a
full `db.rollback()`. A whole-session rollback expires every ORM object the
session is tracking — including the caller's `profile`, which is still in
use elsewhere in the same request (its own cache-key columns, or a sibling
service call further down the request) — and a later plain attribute read on
an expired object triggers an implicit lazy-load that isn't wrapped in an
awaited call, raising `sqlalchemy.exc.MissingGreenlet`. Rolling back a
SAVEPOINT only undoes the failed insert; the rest of the session's state
(profile included) stays intact.
"""
import asyncio

from sqlalchemy import Select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import is_sqlite

_sqlite_write_lock = asyncio.Lock()
_SQLITE_LOCK_RETRIES = 3


async def add_and_commit_or_fetch_existing(
    db: AsyncSession, row, select_existing: Select
) -> tuple[dict, bool]:
    """Returns (data, was_a_concurrent_race). `row` must have a `.data` dict
    attribute (every *Cache model in app.db.models.cache does)."""

    async def _add_and_commit() -> tuple[dict, bool]:
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
        except IntegrityError:
            result = await db.execute(select_existing)
            existing = result.scalar_one()
            return existing.data, True
        await db.commit()
        return row.data, False

    if not is_sqlite:
        return await _add_and_commit()

    # Even serialized through our own lock, aiosqlite can still surface
    # "database is locked" under enough simultaneous pressure (its busy_timeout
    # budget is per SQLite-level attempt, not per request) — releasing the
    # lock between attempts lets whatever else briefly held the file lock
    # finish and get out of the way. Retrying re-runs the whole
    # select-or-insert cycle, so a since-resolved conflict is picked up via
    # the IntegrityError branch above instead of colliding again.
    for attempt in range(_SQLITE_LOCK_RETRIES):
        try:
            async with _sqlite_write_lock:
                return await _add_and_commit()
        except OperationalError:
            if attempt == _SQLITE_LOCK_RETRIES - 1:
                raise
            await asyncio.sleep(0.3 * (attempt + 1))
    raise AssertionError("unreachable")
