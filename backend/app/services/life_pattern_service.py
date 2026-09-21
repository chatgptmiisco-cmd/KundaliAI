"""Product spec's "richer correlations" — Phase 4: does this user's OWN
confirmed history (app.db.models.life_context.LifeEvent, never an inferred
LifeContextItem) share a dasha lord across 2+ occurrences of the same kind
of event? Reuses the already-computed, already-cached Vimshottari dasha
timeline (dasha_service.get_mahadashas_raw) and the exact interval-lookup
functions (app.astro.dasha's find_current_mahadasha/find_current_antardasha)
already used to find the LIVE dasha — just pointed at each event's own date
instead of "now". This never invents a new astrological rule: it only
reports what dasha period this SPECIFIC user's OWN confirmed events actually
fell under, a plain historical correlation, not a general prediction rule.

Its own file (not tacked onto life_context_service.py) because it genuinely
straddles two domains — LifeEvent history and dasha computation — the same
reason prediction_feedback_service.py got its own file in Phase 2."""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.dasha import find_current_antardasha, find_current_mahadasha
from app.db.models.birth_profile import BirthProfile
from app.schemas.user import BirthDataOut
from app.services import dasha_service, life_context_service

# Which LifeEvent.event_type values belong to which correlation domain — a
# plain grouping of the fixed event-type vocabulary (see
# life_context_service._VALID_EVENT_TYPES), not a new classification.
# "moved_city"/"other" are left out: neither maps cleanly onto one of the
# categories chat.py currently wires this into (see _PATTERN_DOMAIN_BY_
# CATEGORY there).
_EVENT_TYPE_DOMAIN: dict[str, str] = {
    "new_job": "career", "promotion": "career", "started_business": "career",
    "marriage": "relationships", "engagement": "relationships", "breakup": "relationships",
    "became_parent": "family",
}
# Never report a "pattern" from a single data point.
_MIN_OCCURRENCES = 2


def _most_common_if_shared(lords: list[str]) -> tuple[str, int] | None:
    """(lord, how many of `lords` actually share it), or None if nothing
    reaches _MIN_OCCURRENCES — returning the real matching count (not just
    the total number of events checked) is what keeps the caller from
    overstating the pattern when a 3rd event lands under a different lord."""
    if len(lords) < _MIN_OCCURRENCES:
        return None
    counts: dict[str, int] = {}
    for lord in lords:
        counts[lord] = counts.get(lord, 0) + 1
    lord, count = max(counts.items(), key=lambda kv: kv[1])
    return (lord, count) if count >= _MIN_OCCURRENCES else None


async def get_recurring_dasha_pattern(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, user_id: str, domain: str
) -> dict | None:
    """None unless at least 2 of the user's own confirmed events in `domain`
    (career/relationships/family) land under the same Mahadasha or
    Antardasha lord — see _EVENT_TYPE_DOMAIN and _MIN_OCCURRENCES above."""
    events = await life_context_service.get_timeline(db, user_id)
    matching = [e for e in events if _EVENT_TYPE_DOMAIN.get(e["event_type"]) == domain]
    if len(matching) < _MIN_OCCURRENCES:
        return None

    mahadashas = await dasha_service.get_mahadashas_raw(db, profile, birth)
    maha_lords: list[str] = []
    antar_lords: list[str] = []
    for event in matching:
        # Most extracted events only carry a year (see LifeEvent.month's
        # docstring) — mid-year is the least-biased anchor for "which
        # period was active" when the exact month isn't known.
        at = datetime(event["year"], event["month"] or 7, 1, tzinfo=timezone.utc)
        maha = find_current_mahadasha(mahadashas, at)
        if maha is None:
            continue
        maha_lords.append(maha.lord)
        antar = find_current_antardasha(maha, at)
        if antar is not None:
            antar_lords.append(antar.lord)

    shared_mahadasha = _most_common_if_shared(maha_lords)
    shared_antardasha = _most_common_if_shared(antar_lords)
    if shared_mahadasha is None and shared_antardasha is None:
        return None
    return {
        "domain": domain,
        "occurrences": len(matching),
        "shared_mahadasha_lord": shared_mahadasha[0] if shared_mahadasha else None,
        "shared_mahadasha_count": shared_mahadasha[1] if shared_mahadasha else None,
        "shared_antardasha_lord": shared_antardasha[0] if shared_antardasha else None,
        "shared_antardasha_count": shared_antardasha[1] if shared_antardasha else None,
    }
