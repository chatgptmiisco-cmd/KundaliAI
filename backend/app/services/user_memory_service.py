from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_memory import UserMemoryNote

# How many recent notes get pulled into a chat prompt — bounds prompt size
# regardless of how many notes a long-running user accumulates. Raised from 8
# now that user_note capture covers more than just mood/event/worry/plan
# (location, work, family situation, etc.), so more of them are worth
# carrying forward.
_RECENT_NOTES_LIMIT = 12


async def add_note(db: AsyncSession, user_id: str, note: str) -> None:
    db.add(UserMemoryNote(user_id=user_id, note=note))
    await db.commit()


async def get_recent_notes(db: AsyncSession, user_id: str) -> list[str]:
    result = await db.execute(
        select(UserMemoryNote.note)
        .where(UserMemoryNote.user_id == user_id)
        .order_by(UserMemoryNote.created_at.desc())
        .limit(_RECENT_NOTES_LIMIT)
    )
    return list(reversed(result.scalars().all()))
