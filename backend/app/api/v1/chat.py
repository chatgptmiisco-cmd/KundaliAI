from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_birth_profile, require_tier
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.db.models.birth_profile import BirthProfile
from app.db.models.chat import ChatMessage
from app.db.models.user import User
from app.schemas.voice import ChatMessageIn, ChatMessageOut
from app.services import prediction_service, user_service
from app.services.chart_service import get_chart
from app.services.daily_reading_service import get_daily_reading
from app.services.dasha_service import get_current_dasha
from app.services.interpretation.factory import get_interpreter
from app.services.interpretation.templates import (
    detect_answering_rishi,
    message_mentions_career_timing,
    message_mentions_children_timing,
    message_mentions_foreign_travel_timing,
    message_mentions_marriage_timing,
    message_mentions_past_tense,
    message_mentions_wealth_timing,
    message_mentions_year_ahead,
    resolve_past_reference,
)

router = APIRouter(prefix="/chat", tags=["chat"])

_HISTORY_LIMIT = 20


@router.post("/astro", response_model=ChatMessageOut)
@limiter.limit("10/minute")
async def chat_astro(
    request: Request,
    body: ChatMessageIn,
    user: User = Depends(get_current_user),
    profile: BirthProfile = Depends(require_birth_profile),
    db: AsyncSession = Depends(get_db),
    _tier=Depends(require_tier("strategy")),
):
    hi = body.language == "hi"
    birth = user_service.decrypt_birth_data(profile)
    chart = await get_chart(db, profile, birth, "D1")
    current_dasha = await get_current_dasha(db, profile, birth)
    daily = await get_daily_reading(db, profile, birth, date.today(), body.language)

    lagna_sign = chart.lagna_sign_name_hi if hi else chart.lagna_sign_name_en
    mahadasha_lord = (current_dasha.mahadasha.lord_name_hi if hi else current_dasha.mahadasha.lord_name_en) if current_dasha else None
    antardasha_lord = (current_dasha.antardasha.lord_name_hi if hi else current_dasha.antardasha.lord_name_en) if current_dasha else None
    context = {
        "lagna_sign": lagna_sign,
        "planets": [
            {
                "planet": p.planet_name_hi if hi else p.planet_name_en,
                "sign": p.sign_name_hi if hi else p.sign_name_en,
                "house": p.house,
                "retrograde": p.retrograde,
            }
            for p in chart.planets
        ],
        # Real, already-computed facts so both the template router and (when
        # enabled) the LLM answer from the same ground truth rather than the
        # LLM inventing its own reading of the raw planet/house list above.
        "house_breakdown": {
            h.house: (h.explanation_hi if hi else h.explanation_en) for h in chart.house_breakdown
        },
        "yogas": [
            {"key": y.key, "name": y.name_hi if hi else y.name_en, "description": y.description_hi if hi else y.description_en}
            for y in chart.yogas
        ],
        "mahadasha_lord": mahadasha_lord,
        "antardasha_lord": antardasha_lord,
        # The raw planet code (e.g. "Sa"), not the display name above — used
        # to look up the real _PERIOD_CONTENT effect one-liner for the
        # "dasha" chat category.
        "antardasha_lord_code": current_dasha.antardasha.lord if current_dasha else None,
        "daily_reading": {
            "rating": daily.rating,
            "rating_reason": daily.rating_reason,
            "brutal_truth": daily.brutal_truth,
            "key_risk": daily.key_risk,
            "key_opportunity": daily.key_opportunity,
            "tithi_name": daily.tithi_name,
            "festival": daily.festival,
            "doshas": [d.model_dump() for d in daily.doshas],
        },
        "rishi_id": body.rishi_id,
        # Needed to resolve "when I was N" style past-age references (see
        # message_mentions_past_tense/resolve_past_reference below) — same
        # convention as every other real fact already threaded through here.
        "birth_year": birth.date_of_birth.year,
    }

    # A past-tense question ("why did my marriage get delayed", "was there a
    # good period for X") searches backward (birth-to-now) instead of
    # forward (now-to-+20yr) — same engine, same window scanner, just
    # different bounds (see prediction_service._search_bounds). Resolved
    # once per message since it applies uniformly to whichever category(ies)
    # actually match.
    direction: prediction_service.Direction = "past" if message_mentions_past_tense(body.message) else "future"

    # Only fetched when the message actually needs it (real "when will I get
    # married" / "how's my year" questions) — both are Prediction Engine
    # calls, DB-cached after first computation, but skipping them on every
    # unrelated chat message avoids paying that cost (or the first-computation
    # ephemeris/dasha-scan latency) needlessly.
    if message_mentions_marriage_timing(body.message):
        marriage_timing = await prediction_service.get_marriage_timing(db, profile, birth, body.language, direction)
        context["marriage_timing_direction"] = direction
        context["marriage_timing_windows"] = [
            {
                "start_date": w.start_date.isoformat(),
                "end_date": w.end_date.isoformat(),
                "reason": w.reason,
                "antardasha_lord_name": w.antardasha_lord_name,
                "transit_corroborated": w.transit_corroborated,
            }
            for w in marriage_timing.windows
        ]

    # Career/wealth/children/foreign-travel timing — same conditional-fetch
    # pattern as marriage timing above, one block per event type since each
    # needs its own get_life_event_timing(event_type=...) call.
    _LIFE_EVENT_CHECKS = (
        ("career", message_mentions_career_timing, "career_timing"),
        ("wealth", message_mentions_wealth_timing, "wealth_timing"),
        ("children", message_mentions_children_timing, "children_timing"),
        ("foreign_travel", message_mentions_foreign_travel_timing, "foreign_travel_timing"),
    )
    for event_type, mentions_fn, category in _LIFE_EVENT_CHECKS:
        if mentions_fn(body.message):
            life_event = await prediction_service.get_life_event_timing(
                db, profile, birth, event_type, body.language, direction
            )
            context[f"{category}_direction"] = direction
            context[f"{category}_windows"] = [
                {
                    "start_date": w.start_date.isoformat(),
                    "end_date": w.end_date.isoformat(),
                    "reason": w.reason,
                    "antardasha_lord_name": w.antardasha_lord_name,
                    "transit_corroborated": w.transit_corroborated,
                }
                for w in life_event.windows
            ]

    # The general "what was going on then" reflection — only fires when a
    # past reference actually resolves to a real date (never guessed); a
    # past-tense question already answered by one of the categories above
    # (marriage/career/etc.) doesn't also need this generic fallback.
    if (
        direction == "past"
        and not any(mentions_fn(body.message) for _, mentions_fn, _ in _LIFE_EVENT_CHECKS)
        and not message_mentions_marriage_timing(body.message)
    ):
        target_date = resolve_past_reference(body.message, birth.date_of_birth.year, datetime.now(timezone.utc).year)
        if target_date is not None:
            life_theme = await prediction_service.get_life_theme(db, profile, birth, target_date, body.language)
            context["life_theme"] = {"theme": life_theme.theme, "rating": life_theme.rating}

    if message_mentions_year_ahead(body.message):
        current_year = datetime.now(timezone.utc).year
        year_ahead = await prediction_service.get_year_ahead(db, profile, birth, current_year, body.language)
        today = date.today()
        current_quarter = next(
            (q for q in year_ahead.quarters if q.start_date <= today <= q.end_date), None
        )
        context["year_ahead"] = {
            "year": year_ahead.year,
            "overall_rating": year_ahead.overall_rating,
            "overall_theme": year_ahead.overall_theme,
            "current_quarter_opportunity": current_quarter.opportunities[0] if current_quarter and current_quarter.opportunities else None,
            "current_quarter_risk": current_quarter.risks[0] if current_quarter and current_quarter.risks else None,
        }

    # History is scoped per-Rishi (matches the frontend's separate
    # conversation-per-Rishi state) so Vasishtha never sees what the user
    # asked Gargi, and vice versa.
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id, ChatMessage.rishi_id == body.rishi_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(_HISTORY_LIMIT)
    )
    history_rows = list(reversed(result.scalars().all()))
    history = [{"role": row.role, "content": row.content} for row in history_rows]
    history.append({"role": "user", "content": body.message})

    interpreter = get_interpreter()
    reply = await interpreter.chat_reply(history, context, body.language)
    # Which real specialist "owns" this question's topic — computed
    # independently of which persona actually answered (see
    # detect_answering_rishi), so it's a stable attribution label even when
    # the generalist "vyasa" persona is the one chatting.
    answered_by_rishi_id = detect_answering_rishi(body.message, birth.date_of_birth.year)

    db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
    db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id))
    await db.commit()

    return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=answered_by_rishi_id)
