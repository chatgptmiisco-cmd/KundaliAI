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
from app.services import prediction_service, user_memory_service, user_service
from app.services.chart_service import get_chart
from app.services.chat_understanding import classify_message, compute_out_of_domain_redirects
from app.services.daily_reading_service import get_daily_reading
from app.services.dasha_service import get_current_dasha
from app.services.interpretation.factory import get_interpreter
from app.services.interpretation.templates import (
    _RISHI_DOMAIN_EN,
    _RISHI_DOMAIN_HI,
    _TOPIC_TIMING_COUNTERPART,
    build_greeting_reply,
    detect_answering_rishi,
    message_is_greeting,
    message_mentions_past_tense,
    resolve_past_reference,
)

router = APIRouter(prefix="/chat", tags=["chat"])

_HISTORY_LIMIT = 20
# (event_type for prediction_service.get_life_event_timing, category name the
# classifier/regex-fallback may return)
_LIFE_EVENT_CHECKS = (
    ("career", "career_timing"),
    ("wealth", "wealth_timing"),
    ("children", "children_timing"),
    ("foreign_travel", "foreign_travel_timing"),
    ("career_promotion", "career_promotion_timing"),
    ("business_expansion", "business_expansion_timing"),
    ("business_partnership", "business_partnership_timing"),
)
_DECISION_CHECKS = (
    ("job_change", "job_change_decision"),
    ("business_start", "business_start_decision"),
)
# Reverse of _TOPIC_TIMING_COUNTERPART ({"career": "career_timing", ...}) —
# used below to also fetch real timing windows when the plain topic was
# asked ("what does my chart say about my career") even though the message
# never separately asked "when", so the reply can include a genuine future
# timeline alongside the static house-based read.
_TIMING_TO_TOPIC = {v: k for k, v in _TOPIC_TIMING_COUNTERPART.items()}


def _planet_technical(chart, planet_code: str, hi: bool) -> dict:
    """Raw technical facts for one planet, from chart.planet_themes — its
    display name, which house(s) it itself rules, and which house/sign it's
    actually placed in. Feeding these numbers/names directly (rather than
    only the paraphrased theme_en/hi prose) is what lets chat state things
    like "your 10th house is Taurus, ruled by Venus, which sits in your 4th
    house, Scorpio" instead of a softened "home and family" life-area
    phrase — per direct feedback, naming the real houses/signs read as more
    personal, not more confusing."""
    theme = chart.planet_themes[planet_code]
    return {
        "planet_name": theme.name_hi if hi else theme.name_en,
        "rules_houses": theme.ruled_houses,
        "placed_house": theme.placed_house,
        "placed_sign": theme.placed_sign_hi if hi else theme.placed_sign_en,
    }


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
        # Plain-language good/bad/mixed verdict per house, no planet names or
        # astrology terms — this (not the detailed explanation above) is what
        # a static "what does my chart say about X" chat answer uses; the
        # detailed version stays available for the dedicated chart-
        # explanation screen, a different reading context from a quick
        # chat answer.
        "house_verdict": {
            h.house: (h.verdict_hi if hi else h.verdict_en) for h in chart.house_breakdown
        },
        # The real, chart-specific technical facts behind each house's ruling
        # planet — its name, which house(s) it itself rules, and which house/
        # sign it's actually placed in (see _planet_technical below). This is
        # what a topic answer actually leans on now: naming the real house
        # numbers and sign names, not just a paraphrased "home and family"
        # life-area phrase, and not just the generic mahadasha/antardasha
        # description that's identical no matter which topic is asked about.
        "house_technical": {
            h.house: {"house_sign": h.sign_name_hi if hi else h.sign_name_en, **_planet_technical(chart, h.lord, hi)}
            for h in chart.house_breakdown
        },
        "yogas": [
            {
                "key": y.key,
                "name": y.name_hi if hi else y.name_en,
                "description": y.description_hi if hi else y.description_en,
                # Plain "yes, you have this" version — used by chat's dosha/
                # yoga answers instead of description above, which stays
                # available for the dedicated chart-explanation screen.
                "chat_summary": y.chat_summary_hi if hi else y.chat_summary_en,
            }
            for y in chart.yogas
        ],
        "mahadasha_lord": mahadasha_lord,
        "antardasha_lord": antardasha_lord,
        # The raw planet code (e.g. "Sa"), not the display name above — used
        # to look up the real _PERIOD_CONTENT effect one-liner for the
        # "dasha" chat category.
        "antardasha_lord_code": current_dasha.antardasha.lord if current_dasha else None,
        # Same signification-blend sentence as house_lord_theme above, but
        # looked up by planet code — a dasha lord isn't necessarily any
        # topic's house-lord (Rahu/Ketu never are), so this is what actually
        # explains WHY the current Mahadasha/Antardasha matters for this
        # specific chart, instead of a generic "challenges and risks" line
        # that would fit any chart's Rahu-Saturn period.
        "mahadasha_lord_technical": (
            _planet_technical(chart, current_dasha.mahadasha.lord, hi) if current_dasha else None
        ),
        "antardasha_lord_technical": (
            _planet_technical(chart, current_dasha.antardasha.lord, hi) if current_dasha else None
        ),
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
        # resolve_past_reference below) — same convention as every other
        # real fact already threaded through here.
        "birth_year": birth.date_of_birth.year,
    }

    # History is scoped per-Rishi (matches the frontend's separate
    # conversation-per-Rishi state) so Vasishtha never sees what the user
    # asked Gargi, and vice versa. Fetched before classification since
    # understanding a message (especially a reply to an earlier clarifying
    # question) needs the whole conversation, not just the latest line.
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id, ChatMessage.rishi_id == body.rishi_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(_HISTORY_LIMIT)
    )
    history_rows = list(reversed(result.scalars().all()))

    # A brand-new conversation opened with nothing but a greeting ("hi",
    # "namaste") gets a warm hello back introducing this persona, instead of
    # being run through classification/engine calls it was never actually
    # asking for. A greeting later in an existing conversation isn't special-
    # cased here — it still goes through the normal pipeline below.
    if not history_rows and message_is_greeting(body.message):
        reply = build_greeting_reply(body.rishi_id, body.language)
        db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id))
        await db.commit()
        return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=None)

    history = [{"role": row.role, "content": row.content} for row in history_rows]
    history.append({"role": "user", "content": body.message})

    # Decides which real-life categories this message touches — an OpenAI
    # call when configured (see app.services.chat_understanding), otherwise
    # today's exact keyword-matching behaviour. Either way, this is the ONLY
    # thing that decides what to fetch below; the actual facts always come
    # from the real Prediction Engine calls that follow, never from the LLM.
    understanding = await classify_message(history, body.rishi_id, birth.date_of_birth.year, body.language)

    if understanding.needs_clarification and understanding.clarifying_question:
        # Too vague to answer honestly — ask instead of guessing. No engine
        # calls, no interpreter call: nothing to explain yet.
        reply = understanding.clarifying_question
        db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id))
        await db.commit()
        return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=None)

    categories = understanding.categories
    if understanding.user_note:
        await user_memory_service.add_note(db, user.id, understanding.user_note)

    # A past-tense question ("why did my marriage get delayed", "was there a
    # good period for X") searches backward (birth-to-now) instead of
    # forward (now-to-+20yr) — same engine, same window scanner, just
    # different bounds (see prediction_service._search_bounds).
    direction: prediction_service.Direction = "past" if message_mentions_past_tense(body.message) else "future"

    # Only fetched when the message actually needs it (real "when will I get
    # married" / "how's my year" questions) — both are Prediction Engine
    # calls, DB-cached after first computation, but skipping them on every
    # unrelated chat message avoids paying that cost (or the first-computation
    # ephemeris/dasha-scan latency) needlessly.
    if "marriage_timing" in categories or "marriage" in categories:
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
    # business_partnership can come back empty with a `note` (gated by the
    # user's LifeState.business_state — see
    # prediction_service.get_life_event_timing) instead of windows, so that
    # note is threaded into context too, for every category, so the
    # explanation can describe a gate honestly rather than as if nothing
    # was found.
    for event_type, category in _LIFE_EVENT_CHECKS:
        topic_counterpart = _TIMING_TO_TOPIC.get(category)
        if category in categories or (topic_counterpart and topic_counterpart in categories):
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
            if life_event.note:
                context[f"{category}_note"] = life_event.note

    # Decision support ("should I do X now?") — a genuinely different
    # question shape from every timing category above: a verdict +
    # reasoning, not a list of windows. See prediction_service.get_decision.
    for decision_type, category in _DECISION_CHECKS:
        if category in categories:
            decision = await prediction_service.get_decision(db, profile, birth, decision_type, body.language)
            context[f"{decision_type}_decision"] = {
                "verdict": decision.verdict,
                "reasoning": decision.reasoning,
                # mode="json" — start_date/end_date are `date` objects, which
                # a plain model_dump() leaves as-is and json.dumps() can't
                # serialize; this was a latent bug that only ever fired once
                # a real LLM path (which JSON-dumps this context) went live.
                "current_period": decision.current_period.model_dump(mode="json") if decision.current_period else None,
                "better_window": decision.better_window.model_dump(mode="json") if decision.better_window else None,
                "history_nudge": decision.history_nudge,
                "note": decision.note,
            }

    # The general "what was going on then" reflection — only fires when a
    # past reference actually resolves to a real date (never guessed).
    # _detect_categories/classify_message both only add "life_theme" when
    # nothing more specific already matched, so this doesn't need its own
    # exclusion check against the categories above.
    if "life_theme" in categories:
        target_date = resolve_past_reference(body.message, birth.date_of_birth.year, datetime.now(timezone.utc).year)
        if target_date is not None:
            life_theme = await prediction_service.get_life_theme(db, profile, birth, target_date, body.language)
            context["life_theme"] = {"theme": life_theme.theme, "rating": life_theme.rating}

    if "year_ahead" in categories:
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

    # Rishi specialization stays a plain deterministic lookup, never
    # something the classifier decides — a category outside this rishi's
    # own domain still gets a real fact fetched above (compound questions
    # spanning two domains both get answered for real), but the interpreter
    # is told which ones to keep to one line + redirect for.
    out_of_domain_redirects = compute_out_of_domain_redirects(categories, body.rishi_id, body.language)
    context["detected_categories"] = categories
    context["out_of_domain_redirects"] = out_of_domain_redirects
    context["rishi_domain"] = (_RISHI_DOMAIN_HI if hi else _RISHI_DOMAIN_EN).get(body.rishi_id)
    # Short facts remembered about this user from earlier conversations
    # (any Rishi) — see app.services.user_memory_service — for
    # personalization; never treated as ground truth for the chart itself.
    context["user_memory"] = await user_memory_service.get_recent_notes(db, user.id)

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
