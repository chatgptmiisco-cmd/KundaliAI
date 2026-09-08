"""Generates the "does this match your past" validation questions shown right
after onboarding — each one is a real, already-elapsed Antardaśā from this
specific chart's own Vimshottari timeline, not a generic personality
statement. The whole point is that the astrology engine is asked "what did
you predict for this window", and the answer is checked against something the
person can actually remember, instead of a vague "does this sound like you".

No LLM involved: house-lord placement + planetary dignity + the dasha
timeline are all already-computed facts (see app.astro.dasha /
app.astro.natal_insights); this module only phrases them as a question.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.constants import PLANET_NAMES_EN, PLANET_NAMES_HI, PlanetKey
from app.astro.dasha import Antardasha
from app.astro.natal_insights import planet_dignity
from app.db.models.birth_profile import BirthProfile
from app.schemas.user import BirthDataOut
from app.schemas.validation import ValidationQuestion, ValidationQuestionsResponse
from app.services.chart_service import get_chart
from app.services.dasha_service import get_mahadashas_raw
from app.services.interpretation.templates import (
    _DIGNITY_QUALIFIER_EN,
    _DIGNITY_QUALIFIER_HI,
    _FOCUS_BY_HOUSE_EN,
    _FOCUS_BY_HOUSE_HI,
    _hindi_house,
    _ordinal,
)

MAX_QUESTIONS = 4
MIN_ANTARDASHA_DAYS = 60  # shorter windows are too vague to ask "did X happen then"

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


def _select_diverse_antardashas(antardashas: list[Antardasha], now: datetime, max_count: int) -> list[Antardasha]:
    completed = [a for a in antardashas if a.end <= now and (a.end - a.start) >= timedelta(days=MIN_ANTARDASHA_DAYS)]
    if len(completed) <= max_count:
        return completed
    # Evenly spaced across the person's life so far (childhood through now),
    # rather than four adjacent sub-periods from the same Mahadasha — always
    # keeping the most recent completed one for relevance.
    step = len(completed) / max_count
    indices = sorted({int(i * step) for i in range(max_count)})
    indices[-1] = len(completed) - 1
    return [completed[i] for i in indices]


def _build_statement(lord: PlanetKey, house: int, dignity: str, start: datetime, end: datetime, language: str) -> str:
    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
    focus = (_FOCUS_BY_HOUSE_HI if language == "hi" else _FOCUS_BY_HOUSE_EN)[house]
    qualifier = (_DIGNITY_QUALIFIER_HI if language == "hi" else _DIGNITY_QUALIFIER_EN)[dignity]
    lord_name = names[lord]
    start_label = _format_date(start, language)
    end_label = _format_date(end, language)

    if language == "hi":
        return (
            f"{start_label} से {end_label} के बीच आपकी {lord_name} अंतर्दशा चल रही थी — "
            f"{lord_name} आपके {_hindi_house(house)} में है और {qualifier}, इसलिए इस दौर में ध्यान "
            f"{focus} की ओर रहा होगा। क्या इस दौरान आपने ऐसा कुछ अनुभव किया?"
        )
    return (
        f"Between {start_label} and {end_label}, your {lord_name} Antardasha was running — "
        f"{lord_name} sits in your {_ordinal(house)} house and is {qualifier}, so this window "
        f"should have pulled toward {focus}. Did you notice something like that during that time?"
    )


async def get_validation_questions(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, language: str
) -> ValidationQuestionsResponse:
    d1 = await get_chart(db, profile, birth, "D1")
    planet_sign_index = {p.planet: p.sign_index for p in d1.planets}
    planet_house = {p.planet: p.house for p in d1.planets}

    mahadashas = await get_mahadashas_raw(db, profile, birth)
    all_antardashas = [a for m in mahadashas for a in m.antardashas]

    now = datetime.now(timezone.utc)
    selected = _select_diverse_antardashas(all_antardashas, now, MAX_QUESTIONS)

    questions = []
    for a in selected:
        house = planet_house[a.lord]
        dignity = planet_dignity(a.lord, planet_sign_index[a.lord])
        questions.append(
            ValidationQuestion(
                period_start=a.start.date().isoformat(),
                period_end=a.end.date().isoformat(),
                lord=a.lord,
                house=house,
                statement=_build_statement(a.lord, house, dignity, a.start, a.end, language),
            )
        )

    return ValidationQuestionsResponse(language=language, questions=questions)
