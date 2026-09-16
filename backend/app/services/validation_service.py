"""Generates the "does this match your past" validation questions shown right
after onboarding — each one is a real, already-elapsed Antardaśā from this
specific chart's own Vimshottari timeline, not a generic personality
statement. The whole point is that the astrology engine is asked "what did
you predict for this window", and the answer is checked against something the
person can actually remember, instead of a vague "does this sound like you".

Windows are restricted to periods the person can plausibly recall: they must
have already been old enough (not infancy/early childhood) and the window
must be recent (not decades-old), otherwise the question is unanswerable and
looks broken even when the underlying astrology is correct.

No LLM involved: house-lord placement + the dasha timeline are already-
computed facts (see app.astro.dasha); this module only phrases them as a
plain-language question — deliberately without astrology jargon (no
"Antardasha", house numbers, or dignity terms), since the person answering
just needs to recognize a real period in their life, not follow the
astrology.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.constants import PLANET_NAMES_EN, PLANET_NAMES_HI, PlanetKey
from app.astro.dasha import Antardasha
from app.db.models.birth_profile import BirthProfile
from app.schemas.user import BirthDataOut
from app.schemas.validation import ValidationQuestion, ValidationQuestionsResponse
from app.services.chart_service import get_chart
from app.services.dasha_service import get_mahadashas_raw
from app.services.interpretation.templates import _FOCUS_BY_HOUSE_EN, _FOCUS_BY_HOUSE_HI

MAX_QUESTIONS = 4
MIN_ANTARDASHA_DAYS = 60  # shorter windows are too vague to ask "did X happen then"
MIN_AGE_YEARS_AT_START = 7  # below this, there's rarely a real memory to check against
MAX_YEARS_AGO = 10  # per product requirement: keep questions recent enough to recall clearly
_DAYS_PER_YEAR = 365.25

_MONTHS_EN = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]
_MONTHS_HI = [
    "जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून",
    "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर",
]


def _format_date(dt: datetime, language: str) -> str:
    months = _MONTHS_HI if language == "hi" else _MONTHS_EN
    return f"{months[dt.month - 1]} {dt.year}"


def _evenly_spaced(candidates: list[Antardasha], max_count: int) -> list[Antardasha]:
    if len(candidates) <= max_count:
        return candidates
    # Evenly spaced across the eligible range rather than four adjacent
    # sub-periods from the same Mahadasha — always keeping the most recent
    # one for relevance.
    step = len(candidates) / max_count
    indices = sorted({int(i * step) for i in range(max_count)})
    indices[-1] = len(candidates) - 1
    return [candidates[i] for i in indices]


def _select_diverse_antardashas(
    antardashas: list[Antardasha], birth_date: date, now: datetime, max_count: int
) -> list[Antardasha]:
    completed = [a for a in antardashas if a.end <= now and (a.end - a.start) >= timedelta(days=MIN_ANTARDASHA_DAYS)]

    def age_at_start(a: Antardasha) -> float:
        return (a.start.date() - birth_date).days / _DAYS_PER_YEAR

    def years_ago_at_end(a: Antardasha) -> float:
        return (now - a.end).days / _DAYS_PER_YEAR

    # Strict: old enough at the time to actually remember it, and recent
    # enough now to recall clearly.
    relatable = [
        a for a in completed
        if age_at_start(a) >= MIN_AGE_YEARS_AT_START and years_ago_at_end(a) <= MAX_YEARS_AGO
    ]
    if relatable:
        return _evenly_spaced(relatable, max_count)

    # Fall back to "old enough to remember" without the recency cap, for
    # charts where every memorable period happens to be more than 10 years
    # back (e.g. an older user who signed up long after those periods ran).
    old_enough = [a for a in completed if age_at_start(a) >= MIN_AGE_YEARS_AT_START]
    if old_enough:
        return _evenly_spaced(old_enough, max_count)

    # Last resort (e.g. a very young user with no eligible window yet): any
    # already-completed period is still better than asking nothing at all.
    return _evenly_spaced(completed, max_count)


def _build_statement(lord: PlanetKey, house: int, start: datetime, end: datetime, language: str) -> str:
    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
    focus = (_FOCUS_BY_HOUSE_HI if language == "hi" else _FOCUS_BY_HOUSE_EN)[house]
    lord_name = names[lord]
    start_label = _format_date(start, language)
    end_label = _format_date(end, language)

    if language == "hi":
        return (
            f"{start_label} से {end_label} के बीच का समय आपके लिए {lord_name} से जुड़ा रहा — "
            f"ऐसे दौर में अक्सर ध्यान {focus} की ओर चला जाता है। क्या आपने उस दौरान ऐसा कुछ महसूस किया?"
        )
    return (
        f"Between {start_label} and {end_label}, this was a {lord_name}-linked period for you — "
        f"times like this often pull your attention toward {focus}. Did you notice something like "
        f"that around then?"
    )


async def get_validation_questions(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, language: str
) -> ValidationQuestionsResponse:
    d1 = await get_chart(db, profile, birth, "D1")
    planet_house = {p.planet: p.house for p in d1.planets}

    mahadashas = await get_mahadashas_raw(db, profile, birth)
    all_antardashas = [a for m in mahadashas for a in m.antardashas]

    now = datetime.now(timezone.utc)
    selected = _select_diverse_antardashas(all_antardashas, birth.date_of_birth, now, MAX_QUESTIONS)

    questions = []
    for a in selected:
        house = planet_house[a.lord]
        questions.append(
            ValidationQuestion(
                period_start=a.start.date().isoformat(),
                period_end=a.end.date().isoformat(),
                lord=a.lord,
                house=house,
                statement=_build_statement(a.lord, house, a.start, a.end, language),
            )
        )

    return ValidationQuestionsResponse(language=language, questions=questions)
