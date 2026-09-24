import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_birth_profile, require_tier
from app.astro.natal_insights import compute_natal_insights
from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.db.models.birth_profile import BirthProfile
from app.db.models.chat import ChatMessage
from app.db.models.user import User
from app.schemas.voice import ChatMessageIn, ChatMessageOut
from app.services import (
    chat_memory_service, important_date_service, life_context_service, life_pattern_service,
    prediction_feedback_service, prediction_service, user_service,
)
from app.services.chart_service import get_chart
from app.services.chat_understanding import classify_message, compute_out_of_domain_redirects, relevant_domains
from app.services.daily_reading_service import get_daily_reading
from app.services.dasha_service import get_current_dasha
from app.services import conversation_engine, user_context_engine, native_response, chat_beautifier, chat_gpt_mediator, question_strategy
from app.core.config import get_settings
from app.services.interpretation.factory import native_chat
from app.services.interpretation.templates import (
    _RISHI_DOMAIN_EN,
    _RISHI_DOMAIN_HI,
    _TOPIC_TIMING_COUNTERPART,
    build_greeting_reply,
    build_returning_greeting_reply,
    detect_answering_rishi,
    message_is_affirmative_reply,
    message_is_greeting,
    message_is_negative_reply,
    message_mentions_past_tense,
    resolve_past_reference,
    wants_technical_detail,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = get_logger(__name__)

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
    # house_purchase (Phase 5) is generic in prediction_service.get_decision
    # (new EventType="property" + karakas), but Phase 8 pulled
    # house_purchase_decision OUT of this loop — it now gets its own block
    # below (like marriage_decision) calling the richer, reference-based
    # get_property_analysis instead. get_decision itself still supports
    # "house_purchase" unchanged, for the plain /prediction/decision REST
    # endpoint's existing contract.
)
# Reverse of _TOPIC_TIMING_COUNTERPART ({"career": "career_timing", ...}) —
# used below to also fetch real timing windows when the plain topic was
# asked ("what does my chart say about my career") even though the message
# never separately asked "when", so the reply can include a genuine future
# timeline alongside the static house-based read.
_TIMING_TO_TOPIC = {v: k for k, v in _TOPIC_TIMING_COUNTERPART.items()}
# Which life_pattern_service correlation domain each category maps to — see
# life_pattern_service._EVENT_TYPE_DOMAIN for the matching LifeEvent types.
_PATTERN_DOMAIN_BY_CATEGORY = {
    "career_timing": "career", "career_promotion_timing": "career",
    "job_change_decision": "career", "business_start_decision": "career",
    "marriage_timing": "relationships", "children_timing": "family",
    "marriage_decision": "relationships",
}


_DECISION_LABEL_EN = {
    "job_change": "leaving your job", "business_start": "starting your business",
    "house_purchase": "buying a house", "marriage": "getting married",
}
_DECISION_LABEL_HI = {
    "job_change": "नौकरी छोड़ने", "business_start": "अपना व्यवसाय शुरू करने",
    "house_purchase": "घर खरीदने", "marriage": "विवाह करने",
}


def _build_outcome_checkin_question(decision, language: str) -> str:
    """Product spec §12 — Outcome Follow-Ups: deterministic (not LLM-
    written) so chat_understanding can reliably recognize its own question
    later just by it being the most recent assistant turn in history, and
    so it never accidentally invents details about a decision it's asking
    about. See life_context_service.get_decisions_due_for_outcome_checkin
    for when this actually fires."""
    if language == "hi":
        label = _DECISION_LABEL_HI.get(decision.decision_type, "इस फ़ैसले")
        return f"वैसे, कुछ समय पहले आप {label} पर विचार कर रहे थे। अब तक कैसा रहा — जैसा सोचा था उससे बेहतर, बुरा, या करीब-करीब वैसा ही?"
    label = _DECISION_LABEL_EN.get(decision.decision_type, "that decision")
    prefix = "Waise, " if language == "hinglish" else "By the way — "
    return (
        f"{prefix}a while back you were weighing {label}. How's it gone so far — better, "
        "worse, or about what you expected?"
    )


def _build_reconfirm_question(item, language: str) -> str:
    """Product spec §13 — Context Decay: deterministic (not LLM-written),
    same reasoning as _build_outcome_checkin_question above — this exact
    text becomes the most recent assistant turn in history, so
    chat_understanding can reliably recognize a reply to it as answering
    this specific fact rather than starting a new topic."""
    if language == "hi":
        return (
            f"बस एक छोटी जांच — आपने कुछ समय पहले बताया था: \"{item.value}\"। "
            "क्या यह अब भी वैसा ही है, या कुछ बदल गया है?"
        )
    prefix = "Ek chhota check — " if language == "hinglish" else "Quick check-in — "
    return f"{prefix}you'd mentioned this a while back: \"{item.value}\". Still the case, or has it changed?"


def _build_important_date_checkin_question(item, language: str) -> str:
    """Phase 5 — deterministic (not LLM-written), same reasoning as
    _build_outcome_checkin_question/_build_reconfirm_question above: this
    exact text becomes the most recent assistant turn in history, so
    chat_understanding can reliably recognize a reply to it as answering
    this specific date rather than starting a new topic."""
    date_str = item.target_date.isoformat()
    if language == "hi":
        return f"वैसे, आपने \"{item.description}\" ({date_str}) का ज़िक्र किया था — उसका क्या हुआ?"
    prefix = "Waise, " if language == "hinglish" else "By the way — "
    return f"{prefix}you'd mentioned \"{item.description}\" around {date_str}. How did that go?"


def _window_context(w) -> dict:
    """A MarriageWindow/LifeEventWindow, trimmed to what the chat LLM
    actually needs — previously only start/end/reason/antardasha_lord_name/
    transit_corroborated reached this far, discarding evidence_level/
    confidence/literal_event_plausible/peak_window even though the engine
    already computes all of them on every window. See openai_interpreter.
    chat_reply's prompt for how these get used (hedge on weak evidence,
    reinterpret when a literal reading isn't age-plausible)."""
    out = {
        "start_date": w.start_date.isoformat(),
        "end_date": w.end_date.isoformat(),
        "reason": w.reason,
        "antardasha_lord_name": w.antardasha_lord_name,
        "transit_corroborated": w.transit_corroborated,
        "evidence_level": w.evidence_level,
        "confidence": w.confidence,
        "literal_event_plausible": w.literal_event_plausible,
    }
    if w.peak_window:
        out["peak_window"] = {
            "start_date": w.peak_window.start_date.isoformat(),
            "end_date": w.peak_window.end_date.isoformat(),
        }
    return out


def _long_term_peak_context(peak) -> dict:
    return {
        "start_date": peak.start_date.isoformat(),
        "end_date": peak.end_date.isoformat(),
        "antardasha_lord_name": peak.antardasha_lord_name,
    }


# Product spec §13/§17 — a vague "what happened in my past" defaults to the
# recent past — PRIMARILY the last 5 years, widening to 10 only when
# nothing at all falls in that tighter window (never further, and never
# past the user's own birth year) — rather than surfacing a childhood-era
# window just because it happens to score highest classically.
_RECENT_PAST_YEARS_PRIMARY = 5
_RECENT_PAST_YEARS_FALLBACK = 10
_CONFIDENCE_RANK = {"strong": 2, "moderate": 1, "low": 0}
# Product spec §20 — Cross-Domain Events: how much two windows' date ranges
# have to overlap (as a fraction of the SHORTER one) before they're treated
# as one combined life theme rather than two unrelated candidates the
# selection logic just picks the stronger of.
_OVERLAP_FRACTION_THRESHOLD = 0.3


def _best_recent_window(windows, horizon_start_year: int):
    recent = [w for w in windows if w.start_date.year >= horizon_start_year]
    if not recent:
        return None
    return max(recent, key=lambda w: (_CONFIDENCE_RANK[w.confidence], w.score))


def _overlap_fraction(a, b) -> float:
    overlap_days = (min(a.end_date, b.end_date) - max(a.start_date, b.start_date)).days
    if overlap_days <= 0:
        return 0.0
    shorter_days = min((a.end_date - a.start_date).days, (b.end_date - b.start_date).days)
    return overlap_days / shorter_days if shorter_days > 0 else 0.0


async def _recent_past_candidate(db, profile, birth, language: str) -> dict | None:
    """The best real candidate(s) — career and/or marriage/relationship —
    for an open-ended past question, reusing the exact same past-direction
    engine calls chat.py already makes for explicit timing questions — no
    new astrology, just a different selection rule (recency-preferring, not
    highest-score-anywhere) applied to windows the engine already computed.
    When the two domains' best recent windows genuinely overlap in time
    (see _OVERLAP_FRACTION_THRESHOLD), returns ONE combined candidate
    spanning both (product spec §20 — Cross-Domain Events) instead of
    picking whichever domain scored higher and discarding the other."""
    current_year = datetime.now(timezone.utc).year

    marriage_timing = await prediction_service.get_marriage_timing(db, profile, birth, language, "past")
    career_timing = await prediction_service.get_life_event_timing(db, profile, birth, "career", language, "past")

    # Two passes over the SAME already-fetched windows — no new engine
    # calls — preferring the tighter, more memorable 5-year horizon and
    # only widening to 10 when nothing at all falls in it.
    relationship_best = career_best = None
    for years_back in (_RECENT_PAST_YEARS_PRIMARY, _RECENT_PAST_YEARS_FALLBACK):
        horizon_start_year = max(birth.date_of_birth.year, current_year - years_back)
        relationship_best = _best_recent_window(marriage_timing.windows, horizon_start_year)
        career_best = _best_recent_window(career_timing.windows, horizon_start_year)
        if relationship_best is not None or career_best is not None:
            break

    if relationship_best is not None and career_best is not None:
        if _overlap_fraction(relationship_best, career_best) >= _OVERLAP_FRACTION_THRESHOLD:
            start = max(relationship_best.start_date, career_best.start_date)
            end = min(relationship_best.end_date, career_best.end_date)
            confidence = min(
                relationship_best.confidence, career_best.confidence, key=lambda c: _CONFIDENCE_RANK[c]
            )
            return {
                "domains": ["career", "relationships"],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "reason": f"{career_best.reason} At the same time: {relationship_best.reason}",
                "confidence": confidence,
            }

    named = [("career", career_best), ("relationships", relationship_best)]
    named = [(domain, w) for domain, w in named if w is not None]
    if not named:
        return None
    domain, best = max(named, key=lambda pair: (_CONFIDENCE_RANK[pair[1].confidence], pair[1].score))
    return {
        "domains": [domain],
        "start_date": best.start_date.isoformat(),
        "end_date": best.end_date.isoformat(),
        "reason": best.reason,
        "confidence": best.confidence,
    }


def _current_age(dob: date) -> int:
    today = datetime.now(timezone.utc).date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _context_used_summary(life_state: dict, life_context: dict) -> dict:
    """Compact, human-readable snapshot of what the engine actually knew
    when it decided how to answer this turn — the exact visibility gap a
    real debugging complaint called out: "you cannot see where the failure
    happens" without this. Deliberately only the handful of facts that
    actually change routing (married status, spouse, career/business state,
    family planning), not a full context dump."""
    facts: dict = {}
    if life_state.get("marital_status"):
        facts["marital_status"] = life_state["marital_status"]
    if life_state.get("career_state"):
        facts["career_state"] = life_state["career_state"]
    if life_state.get("business_state") not in (None, "none"):
        facts["business_state"] = life_state["business_state"]
    spouse = (life_context.get("relationships") or {}).get("spouse_name", {}).get("value")
    if spouse:
        facts["spouse_name"] = spouse
    if "planning_intent" in (life_context.get("family") or {}):
        facts["family_planning"] = True
    occupation = (life_context.get("career") or {}).get("occupation", {}).get("value")
    if occupation:
        facts["occupation"] = occupation
    return facts


def _log_reasoning(
    *, user_id: str, rishi_id: str | None, message: str, detected_intent: list[str],
    life_state: dict, life_context: dict, response_type: str,
    blocked_predictions: list[str] | None = None, selected_interpretation: list[str] | None = None,
    previous_intent: list[str] | None = None, used_intent_rescue: bool = False,
) -> None:
    """One log line per turn naming exactly what a debugging session needs:
    what was asked, what the engine knew, what got blocked and why, and what
    it decided to answer with instead — so a wrong-looking reply can be
    diagnosed from the logs directly instead of needing to be reported back
    and reproduced from scratch each time. previous_intent (the prior turn's
    conversation_state["categories"], captured before resume() overwrites
    it) makes an intent switch — or a stale topic wrongly persisting —
    readable straight off the logs instead of reconstructed by hand."""
    logger.info(
        "chat_reasoning_trace",
        extra={
            "user_id": user_id,
            "rishi_id": rishi_id,
            "user_question": message[:200],
            "previous_intent": previous_intent if previous_intent is not None else detected_intent,
            "detected_intent": detected_intent,
            "user_context_used": _context_used_summary(life_state, life_context),
            "blocked_predictions": blocked_predictions or [],
            "selected_interpretation": selected_interpretation or detected_intent,
            "final_response_type": response_type,
            "used_intent_rescue": used_intent_rescue,
        },
    )


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
@native_chat
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
    # Product spec §21 — Astrological Fingerprint: a standing, ambient
    # personalization signal (not gated behind any one category), computed
    # from data already in hand above — no extra DB/ephemeris cost. Reuses
    # the SAME compute_natal_insights already relied on for the Complete
    # Kundali screen (see kundali_service.py), never a new astrological rule.
    natal_insights = compute_natal_insights(
        chart.lagna_sign_index,
        {p.planet: p.sign_index for p in chart.planets},
        {p.planet: p.house for p in chart.planets},
    )
    # Phase 5 fix: NatalInsights.stress_house/stress_planet always name
    # whichever of the 6th/8th/12th lords is LEAST-worst, even when none of
    # the three is genuinely afflicted (severity 0 for all three) — unlike
    # blind_spot_reason, there's no "none" signal built into the field
    # itself. Recomputed here from the same public planet_dignity/
    # combust_planets fields natal_insights.py's own _severity uses
    # internally, so this only surfaces a real affliction, never an
    # invented one — same guard as blind_spot_reason != "none" above.
    _stress_severity = (
        (2 if natal_insights.planet_dignity.get(natal_insights.stress_planet) == "debilitated" else 0)
        + (1 if natal_insights.stress_planet in natal_insights.combust_planets else 0)
    )
    context = {
        "lagna_sign": lagna_sign,
        "strongest_planet": (
            (chart.planet_themes[natal_insights.strongest_planet].name_hi if hi
             else chart.planet_themes[natal_insights.strongest_planet].name_en)
            if natal_insights.strongest_planet else None
        ),
        "weakest_planet": (
            (chart.planet_themes[natal_insights.weakest_planet].name_hi if hi
             else chart.planet_themes[natal_insights.weakest_planet].name_en)
            if natal_insights.weakest_planet else None
        ),
        "decision_style": natal_insights.decision_style,
        # A chart with no real affliction has no genuine blind spot to
        # report — never invented just to fill the field (see
        # NatalInsights.blind_spot_reason's "none" fallback).
        **(
            {
                "blind_spot_planet": (
                    chart.planet_themes[natal_insights.blind_spot_planet].name_hi if hi
                    else chart.planet_themes[natal_insights.blind_spot_planet].name_en
                ),
                "blind_spot_reason": natal_insights.blind_spot_reason,
            }
            if natal_insights.blind_spot_reason != "none" else {}
        ),
        **(
            {
                "stress_house": natal_insights.stress_house,
                "stress_planet": (
                    chart.planet_themes[natal_insights.stress_planet].name_hi if hi
                    else chart.planet_themes[natal_insights.stress_planet].name_en
                ),
            }
            if _stress_severity > 0 else {}
        ),
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
        # Phase 13 (Stage 1) — the user's current chronological age. Nothing
        # in the engine computed this before (existing "age" logic is all
        # about a PREDICTED event's plausibility, never the user's present
        # age) — threaded through now so Stage 2's age-banded phrasing can
        # use it without re-plumbing; not yet consumed by any template.
        "user_age": _current_age(birth.date_of_birth),
    }

    # History is scoped per-Rishi (matches the frontend's separate
    # conversation-per-Rishi state) so Vasishtha never sees what the user
    # asked Gargi, and vice versa. Fetched before classification since
    # understanding a message (especially a reply to an earlier clarifying
    # question) needs the whole conversation, not just the latest line.
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id, ChatMessage.rishi_id == body.rishi_id)
        # `created_at` alone isn't a safe conversation-order key: it's a DB
        # server_default(func.now()), and the user+assistant rows from one
        # turn are always added and committed together — on SQLite that's
        # second-granularity, so same-turn rows routinely tie and the DB is
        # then free to return them in EITHER order, silently scrambling
        # "who said this" for the very next request. `id` is a real
        # autoincrement PK, so it strictly reflects insertion order and
        # breaks every tie correctly; ordering by it directly (not just as
        # a tiebreaker) sidesteps the granularity issue entirely.
        .order_by(ChatMessage.id.desc())
        .limit(_HISTORY_LIMIT)
    )
    history_rows = list(reversed(result.scalars().all()))

    # Product spec §12 (Outcome Follow-Ups) — a decision the user actually
    # settled a while ago and never reported back on takes priority over
    # even a greeting at the start of a brand-new conversation: it's
    # time-sensitive (the whole point is asking while it's still a fresh
    # memory) and this is the natural, low-friction moment to ask, the way
    # a person who remembers you would lead with "hey, how did that go?"
    pending_checkins = await life_context_service.get_decisions_due_for_outcome_checkin(db, user.id)
    if not history_rows and pending_checkins:
        reply = _build_outcome_checkin_question(pending_checkins[0], body.language)
        db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id, used_personalization=True))
        await db.commit()
        return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=None)

    # Product spec §13 (Context Decay) — a material fact (career/business/
    # relationships/money — see life_context_service._RECONFIRM_DOMAINS)
    # that's gone stale enough to no longer be safely trusted gets a quick,
    # low-friction "is this still true?" check, same "pull on next fresh
    # conversation" pattern as the outcome check-in above — second priority
    # to it, since an unreported decision outcome is more time-sensitive
    # than a routine staleness check.
    stale_facts = await life_context_service.get_facts_due_for_reconfirmation(db, user.id)
    if not history_rows and not pending_checkins and stale_facts:
        reply = _build_reconfirm_question(stale_facts[0], body.language)
        db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id, used_personalization=True))
        await db.commit()
        return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=None)

    # Phase 5 — an important date/goal target the user mentioned has since
    # passed and hasn't been checked back on yet: third priority tier,
    # same "pull on next fresh conversation" reasoning as the two checks
    # above. See important_date_service.get_pending_checkin — this same
    # row is reused below (fetched only once) for classify_message's
    # benefit too, since unlike the two checks above it can also be
    # answered later in an ongoing conversation, not just right here.
    pending_important_date = await important_date_service.get_pending_checkin(db, user.id)
    if not history_rows and not pending_checkins and not stale_facts and pending_important_date:
        reply = _build_important_date_checkin_question(pending_important_date, body.language)
        db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id, used_personalization=True))
        await db.commit()
        return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=None)

    # A conversation opened with nothing but a greeting ("hi", "namaste")
    # gets a warm hello back instead of being run through classification/
    # engine calls it was never actually asking for. The very first message
    # ever gets the full persona introduction; a LATER bare greeting ("hi"
    # again, mid-conversation) gets a short, warm nudge instead — caught
    # live: this used to fall through to the generic "I have noted what you
    # shared" fallback (worded for a STATEMENT with no matching category),
    # which makes no sense for a bare hello, and reads even more
    # nonsensical once GPT-beautified ("Thanks for sharing that with me!"
    # — nothing was shared).
    if message_is_greeting(body.message):
        reply = (
            build_greeting_reply(body.rishi_id, body.language) if not history_rows
            else build_returning_greeting_reply(body.language)
        )
        db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id))
        await db.commit()
        return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=None)

    # GPT Mediator Layer (app.services.chat_gpt_mediator), when enabled —
    # cleans up garbled/typo'd phrasing BEFORE native classification, fail-
    # closed to body.message unchanged on any failure or polarity drift.
    # Deliberately scoped to just the two places that drive understanding
    # (history fed to classify_message, and resume()'s own message arg
    # below) — every other reference to body.message in this function
    # (storage, exact-phrase gate checks, quoting) stays on the ORIGINAL
    # text the user actually typed.
    classification_message = await chat_gpt_mediator.normalize_input(body.message, body.language, body.engine_only)
    history = [{"role": row.role, "content": row.content} for row in history_rows]
    history.append({"role": "user", "content": classification_message})

    open_decision_objs = await life_context_service.get_open_decisions(db, user.id)
    open_decisions_for_prompt = [
        {"category": life_context_service.CATEGORY_BY_DECISION_TYPE.get(d.decision_type), "context": d.context}
        for d in open_decision_objs
    ]
    # Product spec §7 — Decision-critical gap-filling has to work the FIRST
    # time a decision is ever raised, not only once it's already tracked as
    # "open" from an earlier conversation (that tracking, above, only
    # happens once the engine's decision call runs later in this same
    # function) — so known facts are fetched for both fixed decision
    # categories unconditionally, independent of whether either is
    # currently open.
    decision_known_facts_for_prompt = {
        category: await life_context_service.get_active_context(db, user.id, relevant_domains([category]))
        for category in life_context_service.CATEGORY_BY_DECISION_TYPE.values()
    }
    pending_checkins_for_prompt = [
        {"decision_type": d.decision_type, "context": d.context} for d in pending_checkins
    ]
    pending_reconfirmation_for_prompt = (
        {"domain": stale_facts[0].domain, "key": stale_facts[0].key, "value": stale_facts[0].value}
        if stale_facts else None
    )
    # The one deterministic table the Prediction Engine itself already
    # gates marriage/children/business predictions on (see
    # prediction_service's already_married/already_has_children/
    # business_state checks) — fetched here so a conversational statement
    # ("I got married in November") can update the SAME row a settings-form
    # edit would, not just the free-form LifeContextItem facts below.
    life_state_row = await user_service.get_life_state(db, user.id)
    current_life_state = user_service.decrypt_life_state(life_state_row) if life_state_row else None
    current_life_state_for_prompt = (
        {
            k: v for k, v in current_life_state.model_dump(mode="json", exclude={"version"}).items()
            if v not in (None, 0, "none")
        }
        if current_life_state else None
    )
    # Product spec §15/§30 — a real, falsifiable past-event question the
    # app itself asked earlier (see the life_theme branch further down and
    # prediction_feedback_service) — fetched unconditionally, same
    # "classify_message decides if THIS message answers it" pattern as
    # pending_reconfirmation above, since the answer can arrive at any
    # point in the conversation, not just at the very start.
    pending_feedback_row = await prediction_feedback_service.get_pending_feedback(db, user.id)
    pending_prediction_feedback_for_prompt = (
        {"question_asked": pending_feedback_row.question_asked, "domain": pending_feedback_row.domain}
        if pending_feedback_row else None
    )
    pending_important_date_for_prompt = (
        {"description": pending_important_date.description, "target_date": pending_important_date.target_date.isoformat()}
        if pending_important_date else None
    )

    # Decides which real-life categories this message touches — an OpenAI
    # call when configured (see app.services.chat_understanding), otherwise
    # today's exact keyword-matching behaviour. Either way, this is the ONLY
    # thing that decides what to fetch below; the actual facts always come
    # from the real Prediction Engine calls that follow, never from the LLM.
    understanding = await classify_message(
        history, body.rishi_id, birth.date_of_birth.year, body.language,
        open_decisions_for_prompt, pending_checkins_for_prompt, pending_reconfirmation_for_prompt,
        decision_known_facts_for_prompt, current_life_state_for_prompt, pending_prediction_feedback_for_prompt,
        pending_important_date_for_prompt,
    )

    _, conversation_state = await conversation_engine.load_state(db, user.id, body.rishi_id)
    # Captured before resume() mutates conversation_state in place — logged
    # alongside the new categories below so an intent switch (or a stale
    # topic wrongly persisting) can be read straight off the logs instead of
    # reconstructed by hand from a bug report.
    previous_intent = list(conversation_state.get("categories", []))
    had_focus = bool(conversation_state.get("focus_pending"))
    confirmed, inactive = question_strategy.resolve_focus(understanding, body.message, conversation_state, body.language)
    for fact in inactive:
        await life_context_service.deactivate_fact(db, user.id, fact["id"])
    if not (had_focus and (confirmed or inactive or conversation_state.get("focus_confirmed"))):
        understanding = conversation_engine.resume(understanding, classification_message, conversation_state, body.language)
    categories = understanding.categories
    # Deterministic fallback for a plain yes/no reply to the career-
    # employment gate question this endpoint itself may have just asked
    # (see prediction_service.get_life_event_timing's career_promotion_
    # blocked note). _fallback_understanding (used whenever OpenAI is
    # unavailable — the state of this whole environment) only ever returns
    # categories, never a life_state_update, so a bare "yes" would
    # otherwise fall through every category check below and dead-end on
    # the exact question the app asked. Matched against that note's own
    # fixed English/Hindi text — never LLM-paraphrased on this path — so
    # this never misfires on an unrelated yes/no. Once OpenAI is available
    # again, classify_message's own life_state_line extraction already
    # handles this turn correctly on its own; this only fills the gap for
    # the no-LLM fallback.
    _prior_assistant_message = (
        history[-2]["content"] if len(history) >= 2 and history[-2]["role"] == "assistant" else ""
    )
    _asked_career_employment_gate = (
        "are you currently employed" in _prior_assistant_message
        or "क्या आप अभी नौकरी में हैं" in _prior_assistant_message
    )
    if _asked_career_employment_gate and message_is_affirmative_reply(body.message):
        understanding.needs_clarification = False
        understanding.clarifying_question = None
        await user_service.apply_life_state_updates(db, user.id, career_state="employed")
        if "career_promotion_timing" not in categories:
            categories = [*categories, "career_promotion_timing"]
    elif _asked_career_employment_gate and message_is_negative_reply(body.message):
        await user_service.apply_life_state_updates(db, user.id, career_state="unemployed")
        reply = (
            "ठीक है, कोई बात नहीं — जब आप दोबारा किसी नौकरी में हों तो मुझसे पदोन्नति के समय के बारे में पूछिए।"
            if body.language == "hi" else
            "Got it, no worries — ask me about promotion timing again once you're back in a role."
        )
        db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id))
        await db.commit()
        return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=None)
    # Intent Rescue Layer — last resort before the fully generic "what do
    # you want to talk about" clarifying question, tried only once every
    # deterministic path (detect_intents, topic continuation, pending
    # menus/slots, domain words) has already come up with NOTHING. GPT picks
    # from a fixed, engine-known category list (see chat_gpt_mediator.
    # _KNOWN_CATEGORIES) — it classifies only, never answers, and a failed
    # or out-of-list result changes nothing: the existing generic fallback
    # still fires exactly as before. Skipped for engine_only / when the
    # mediator is disabled, same gating as every other GPT call in this file.
    used_intent_rescue = False
    if understanding.needs_clarification and not categories and not body.engine_only:
        rescued = await chat_gpt_mediator.classify_unmapped_intent(body.message, previous_intent, body.language)
        if rescued:
            categories = [rescued]
            understanding.categories = categories
            understanding.needs_clarification = False
            understanding.clarifying_question = None
            conversation_state["categories"] = categories
            used_intent_rescue = True
        else:
            # Even the category rescue above found nothing — the
            # deterministic engine genuinely has no template or category
            # for this message. Rather than fall back to the fully generic
            # "what do you want to talk about" question forever, let GPT
            # give a short, honest, plain-language reply instead (see
            # chat_gpt_mediator.answer_unmapped's own docstring for why
            # this can't become a channel for a fabricated astrology
            # claim). Whatever the user actually stated is still captured
            # as a fact the normal way — understanding.context_updates
            # (from extract_knowledge, run on every message regardless of
            # category) gets persisted a few lines below either way.
            unmapped_reply = await chat_gpt_mediator.answer_unmapped(body.message, body.language)
            if unmapped_reply:
                # Retractions applied BEFORE the upsert loop below (and
                # here) so a same-turn re-assertion of the same fact still
                # wins — upsert_fact only supersedes a currently-active row,
                # so retracting first just means a fresh one gets inserted.
                for domain, key in understanding.retracted_facts:
                    await life_context_service.retract_fact(db, user.id, domain, key)
                for update in understanding.context_updates:
                    await life_context_service.upsert_fact(
                        db, user.id, update.domain, update.key, update.value, update.confidence, update.source
                    )
                db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
                db.add(ChatMessage(user_id=user.id, role="assistant", content=unmapped_reply, language=body.language, rishi_id=body.rishi_id))
                await conversation_engine.save_state(db, user.id, body.rishi_id, conversation_state)
                await db.commit()
                return ChatMessageOut(reply=unmapped_reply, language=body.language, answered_by_rishi_id=None)
    # Set inside the life_theme branch below when a vague-past-event
    # candidate is surfaced; the actual PredictionFeedback row is only
    # created once `reply` (the interpreter's real phrasing) exists — see
    # that assignment.
    pending_past_event_candidate = None
    # Caught live: "I don't have a business, it was just an idea" had no
    # effect at all on the already-stored business.stage fact from an
    # earlier turn — it kept being echoed back verbatim turn after turn.
    # Applied BEFORE the upsert loop below so a same-turn re-assertion of
    # the same fact still wins (upsert_fact only supersedes a currently-
    # active row, so retracting first just means a fresh one gets inserted).
    for domain, key in understanding.retracted_facts:
        await life_context_service.retract_fact(db, user.id, domain, key)
    # Every extracted fact gets recorded as structured Life Context (see
    # app.services.life_context_service) — never as a bare "confirmed"
    # fact when the model only inferred it; confidence/source travel with
    # each one so a later verification can promote it, per the product
    # spec's "never treat AI inference as fact" principle.
    for update in understanding.context_updates:
        await life_context_service.upsert_fact(
            db, user.id, update.domain, update.key, update.value, update.confidence, update.source
        )
    # Life Timeline entries (product spec §10) — things that already
    # happened, at a real point in time, as opposed to the current-state
    # facts above.
    for event in understanding.events:
        await life_context_service.add_event(db, user.id, event.event_type, event.description, event.year, event.month)
    # The user reporting they've actually settled one of their open
    # decisions ("I accepted the new job") — starts that decision's Outcome
    # Follow-Up clock (see life_context_service.mark_decision).
    if understanding.decision_update:
        await life_context_service.mark_decision(
            db, user.id, understanding.decision_update.category,
            understanding.decision_update.status, understanding.decision_update.final_choice,
        )
    # Closing the loop on a check-in this endpoint itself asked earlier
    # (see the pending_checkins early-return above) — always against the
    # first decision that was actually offered to the model this turn.
    if understanding.outcome_report and pending_checkins:
        await life_context_service.record_outcome(db, user.id, pending_checkins[0].id, understanding.outcome_report)
    # Closing the loop on a Context Decay reconfirmation this endpoint asked
    # earlier (see the stale_facts early-return above) — same value, just a
    # refreshed last_confirmed_at (see upsert_fact's unchanged-value branch);
    # a fact reported as CHANGED never reaches here, it flows through
    # context_updates above instead so it correctly supersedes the old row.
    if understanding.reconfirmed and stale_facts:
        fact = stale_facts[0]
        await life_context_service.upsert_fact(db, user.id, fact.domain, fact.key, fact.value, "high", "user_confirmed")
    # The bridge this whole feature exists for: a life fact stated in
    # conversation updates the SAME LifeState row prediction_service already
    # reads to redirect marriage/children/business predictions — not just
    # the free-form LifeContextItem facts above, which chat_reply's prose
    # uses but the deterministic engine never sees. Partial merge (see
    # apply_life_state_updates) so stating just one fact never wipes out
    # other, previously-known ones.
    if understanding.life_state_update:
        life_state_fields = {
            k: v for k, v in understanding.life_state_update.__dict__.items() if v is not None
        }
        if life_state_fields:
            await user_service.apply_life_state_updates(db, user.id, **life_state_fields)
    # Product spec §15/§30 — closing the loop on a real, falsifiable
    # past-event question this endpoint asked earlier (see the life_theme
    # branch below and prediction_feedback_service). A confirmed/partial
    # answer becomes a real LifeEvent anchored to the WINDOW'S OWN known
    # start year — more reliable than hoping the general events extraction
    # above independently re-infers the year from a reply like "yes, then"
    # that doesn't restate it. Never touches the astrology calculation
    # itself, per the product spec's "the LLM cannot compensate for
    # incorrect deterministic astrology" principle — this only ever
    # records what the user said happened, as personalization context.
    if understanding.prediction_feedback and pending_feedback_row:
        await prediction_feedback_service.record_feedback(
            db, user.id, pending_feedback_row.id,
            understanding.prediction_feedback.verdict, understanding.prediction_feedback.detail,
        )
        # Phase 10 — surfaced so THIS SAME reply can acknowledge the
        # resolution honestly (spec §41/§42: never defend a wrong
        # prediction, never silently ignore that it was just resolved).
        # Absent on every other turn — same "only present when relevant"
        # convention as blind_spot_planet etc.
        context["resolved_prediction_feedback"] = {
            "verdict": understanding.prediction_feedback.verdict,
            "domain": pending_feedback_row.domain,
            "question_asked": pending_feedback_row.question_asked,
        }
        if understanding.prediction_feedback.verdict in ("correct", "partial") and understanding.prediction_feedback.detail:
            await life_context_service.add_event(
                db, user.id, "other", understanding.prediction_feedback.detail,
                pending_feedback_row.window_start.year,
            )
    # Phase 5 — a real future date/goal the user just stated (see the
    # important_date_update extraction instruction) gets recorded; a
    # malformed target_date from the LLM is dropped rather than crashing
    # the request, same "sanitize at the service boundary" convention as
    # user_service._sanitize_life_state_fields.
    if understanding.important_date_update:
        try:
            parsed_date = date.fromisoformat(understanding.important_date_update.target_date)
        except ValueError:
            parsed_date = None
        if parsed_date is not None:
            await important_date_service.add_important_date(
                db, user.id, understanding.important_date_update.domain,
                understanding.important_date_update.description, parsed_date,
            )
    # Closing the loop on an important-date check-in this endpoint asked
    # earlier (see the pending_important_date early-return above) — same
    # "confirmed answer becomes a real LifeEvent" convention as prediction_
    # feedback just above.
    if understanding.important_date_outcome and pending_important_date:
        await important_date_service.resolve_important_date(
            db, user.id, pending_important_date.id, understanding.important_date_outcome,
        )

    # Persist knowledge before questions. A clarification must never discard
    # facts stated in the same message. Refresh after writes for same-turn use.
    native_context = await user_context_engine.retrieve(db, user.id, categories)
    context.update(native_context)
    context["question_type"] = question_strategy.question_type(body.message, categories)
    relevance_prompt = None if inactive else question_strategy.relevance_question(
        body.message, categories, context, conversation_state, body.language, understanding.context_updates,
    )
    context["life_context"] = question_strategy.usable_facts(context, conversation_state, understanding.context_updates)
    # Historical goals remain available for explicit recall, not current advice.
    if categories != ["memory_recall"]:
        context["goal_history"] = []
    for category in categories:
        if category in conversation_engine.DECISION_SLOTS and not understanding.decision_update:
            await life_context_service.upsert_decision(db, user.id, category, body.message)
    gap_question = None if relevance_prompt or inactive else conversation_engine.questions_for(
        categories, context["life_context"], context["life_state"], conversation_state, body.language,
    )
    await conversation_engine.save_state(db, user.id, body.rishi_id, conversation_state)
    context["follow_up_questions"] = gap_question if context["question_type"] == "decision" else None
    clarification = relevance_prompt or (
        understanding.clarifying_question if understanding.needs_clarification else
        understanding.decision_gap_question or (gap_question if context["question_type"] != "decision" else None)
    )
    if clarification:
        # GPT Mediator Layer (app.services.chat_gpt_mediator), when enabled —
        # simplifies the engine's own question wording for display only.
        # Safe by construction: conversation_engine.resume() binds the
        # user's reply to a pending slot by stored slot ID and numbered
        # position, never by re-parsing this displayed text (see that
        # module's own docstring), and simplify_question fails closed to
        # the original wording if the option count doesn't match exactly.
        if not body.engine_only and not relevance_prompt:
            clarification = await chat_gpt_mediator.simplify_question(clarification, body.language)
        prefix = "" if relevance_prompt else native_response.personal_context(context, body.language)
        reply = (prefix + "\n\n" if prefix else "") + clarification
        if conversation_state.get("pending_intent_menu"):
            response_type = "clarification_menu"
            blocked = [f"{conversation_state['pending_intent_menu']['base_category']}_direct_answer"]
        elif understanding.decision_gap_question or gap_question:
            response_type = "decision_gap_question"
            blocked = ["immediate_decision_verdict"]
        else:
            response_type = "needs_clarification"
            blocked = ["guessed_category"]
        _log_reasoning(
            user_id=user.id, rishi_id=body.rishi_id, message=body.message, detected_intent=categories,
            life_state=context["life_state"], life_context=context["life_context"],
            response_type=response_type, blocked_predictions=blocked, previous_intent=previous_intent,
            used_intent_rescue=used_intent_rescue,
        )
        db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id, used_personalization=bool(prefix)))
        await db.commit()
        return ChatMessageOut(reply=reply, language=body.language, question_type="clarification" if relevance_prompt else context["question_type"])
    context["decision_missing"] = any(
        not conversation_engine.known_slot(slot, context["life_context"])
        for category in categories for slot in conversation_engine.DECISION_SLOTS.get(category, ())
    )
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
        context["marriage_timing_windows"] = [_window_context(w) for w in marriage_timing.windows]
        if marriage_timing.long_term_peak:
            context["marriage_timing_long_term_peak"] = _long_term_peak_context(marriage_timing.long_term_peak)

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
            context[f"{category}_windows"] = [_window_context(w) for w in life_event.windows]
            if life_event.long_term_peak:
                context[f"{category}_long_term_peak"] = _long_term_peak_context(life_event.long_term_peak)
            if life_event.note:
                context[f"{category}_note"] = life_event.note

    # Decision support ("should I do X now?") — a genuinely different
    # question shape from every timing category above: a verdict +
    # reasoning, not a list of windows. See prediction_service.get_decision.
    for decision_type, category in _DECISION_CHECKS:
        if category in categories:
            decision = await prediction_service.get_decision(
                db, profile, birth, decision_type, body.language,
                include_mechanics=wants_technical_detail(body.message),
            )
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
            # Life Context's Decision Memory (see life_context_service) —
            # a separate, persistent object from the astrological verdict
            # above, so a LATER conversation can reference "last time you
            # were exploring this" instead of re-deriving it from scratch.
            await life_context_service.upsert_decision(db, user.id, category, body.message)

    # "Should I relocate?" — relocation_decision has no get_decision verdict
    # engine behind it (see life_context_service._DECISION_TYPE_BY_CATEGORY's
    # comment: no classical house-rule maps "should you move" the way
    # house-lord dasha timing does for job_change/business_start). Reuses the
    # SAME foreign_travel life-event-timing signal the foreign_travel_timing
    # category above already surfaces, rather than inventing a new
    # astrological rule. Still tracked as a real Decision Memory row so
    # outcome follow-ups and gap-filling generalize to it exactly like the
    # two get_decision-backed types (both already read generically off
    # life_context_service's category<->type map).
    if "relocation_decision" in categories:
        # Same flat {category}_windows/_direction/_note/_long_term_peak
        # context shape as the _LIFE_EVENT_CHECKS loop above (not a
        # get_decision-style verdict dict) — both openai_interpreter._chat_
        # facts' suffix loop and templates._life_event_chat_answer already
        # pick these up generically by category name, needing no extra
        # per-category wiring in either place.
        relocation_timing = await prediction_service.get_life_event_timing(
            db, profile, birth, "foreign_travel", body.language, direction
        )
        context["relocation_decision_direction"] = direction
        context["relocation_decision_windows"] = [_window_context(w) for w in relocation_timing.windows]
        if relocation_timing.long_term_peak:
            context["relocation_decision_long_term_peak"] = _long_term_peak_context(relocation_timing.long_term_peak)
        if relocation_timing.note:
            context["relocation_decision_note"] = relocation_timing.note
        await life_context_service.upsert_decision(db, user.id, "relocation_decision", body.message)

    # "Should I get married now?" — deliberately NOT part of the generic
    # _DECISION_CHECKS loop above (unlike house_purchase_decision): marriage
    # already has its OWN dedicated, separately-vetted timing computation
    # (get_marriage_timing), so this calls a thin wrapper over THAT (see
    # prediction_service.get_marriage_decision) instead of routing through
    # get_decision's generic engine, which would mean a second, parallel
    # marriage-timing computation that could disagree with the one
    # marriage_timing_windows already relies on.
    if "marriage_decision" in categories:
        marriage_decision = await prediction_service.get_marriage_decision(
            db, profile, birth, body.language, include_mechanics=wants_technical_detail(body.message),
        )
        context["marriage_decision"] = {
            "verdict": marriage_decision.verdict,
            "reasoning": marriage_decision.reasoning,
            "current_period": marriage_decision.current_period.model_dump(mode="json") if marriage_decision.current_period else None,
            "better_window": marriage_decision.better_window.model_dump(mode="json") if marriage_decision.better_window else None,
            "history_nudge": marriage_decision.history_nudge,
            "note": marriage_decision.note,
        }
        await life_context_service.upsert_decision(db, user.id, "marriage_decision", body.message)

    # "Should I buy a house now?" — Phase 8: house_purchase_decision was
    # pulled OUT of the generic _DECISION_CHECKS loop (unlike Phase 5) to
    # call the richer, reference-based get_property_analysis instead (see
    # its own docstring for the BPHS Ch.48 v.2-4 citation and the full
    # classical/derived evidence discipline). Still builds a
    # DecisionResponse-compatible context["house_purchase_decision"] dict
    # (verdict/reasoning/current_period/better_window) so the existing
    # deterministic TemplateInterpreter path needs zero changes, PLUS the
    # full rich structure under its own key for the LLM path.
    if "house_purchase_decision" in categories:
        property_analysis = await prediction_service.get_property_analysis(
            db, profile, birth, body.language, "property_purchase", direction
        )
        context["house_purchase_decision"] = prediction_service.property_analysis_decision_view(
            property_analysis, body.language
        )
        # The full rich structure (property_promise/evidence/medium_term_
        # window/long_term_peak/astro_strength/event_confidence) — LLM-path
        # only, same convention as every other *_windows fact's extra
        # evidence_level/confidence/literal_event_plausible detail.
        context["property_purchase_analysis"] = property_analysis.model_dump(mode="json")
        await life_context_service.upsert_decision(db, user.id, "house_purchase_decision", body.message)

    # Phase 9 — property_sale/property_inheritance/property_relocation:
    # the SAME reference-based engine as house_purchase_decision above
    # (identical BPHS Ch.48 v.2-4 signal, reinterpreted by intent — see
    # get_property_analysis's own docstring), but NOT tracked as a
    # LifeDecision (these are timing-support questions, not a "should I..."
    # choice the way job/business/marriage/house-purchase decisions are —
    # the existing Outcome Follow-Up convention doesn't fit "when might I
    # inherit property").
    for category, intent in (
        ("property_sale_intent", "property_sale"),
        ("property_inheritance_intent", "property_inheritance"),
        ("property_relocation_intent", "property_relocation"),
    ):
        if category in categories:
            property_intent_analysis = await prediction_service.get_property_analysis(
                db, profile, birth, body.language, intent, direction
            )
            context[category] = prediction_service.property_analysis_decision_view(
                property_intent_analysis, body.language
            )
            context[f"{category}_full"] = property_intent_analysis.model_dump(mode="json")

    # Product spec's "richer correlations" — does the user's OWN confirmed
    # history (never inferred facts) share a dasha lord across 2+ real past
    # events in this same life area? Computed once per domain (not once per
    # category — several categories below share a domain), then attached to
    # every category currently asked about that maps to it. See
    # life_pattern_service for why this is a plain historical correlation,
    # never a new astrological rule.
    pattern_domains_needed = {
        _PATTERN_DOMAIN_BY_CATEGORY[c] for c in categories if c in _PATTERN_DOMAIN_BY_CATEGORY
    }
    for pattern_domain in pattern_domains_needed:
        pattern = await life_pattern_service.get_recurring_dasha_pattern(db, profile, birth, user.id, pattern_domain)
        if pattern is None:
            continue

        def _lord_name(code: str | None) -> str | None:
            if code is None:
                return None
            return chart.planet_themes[code].name_hi if hi else chart.planet_themes[code].name_en

        display_pattern = {
            "domain": pattern["domain"],
            "shared_mahadasha_lord": _lord_name(pattern["shared_mahadasha_lord"]),
            "shared_mahadasha_count": pattern["shared_mahadasha_count"],
            "shared_antardasha_lord": _lord_name(pattern["shared_antardasha_lord"]),
            "shared_antardasha_count": pattern["shared_antardasha_count"],
        }
        for category in categories:
            if _PATTERN_DOMAIN_BY_CATEGORY.get(category) == pattern_domain:
                context[f"{category}_personal_pattern"] = display_pattern

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
        elif message_mentions_past_tense(body.message):
            # Product spec §13 — "Past Event Mode": a genuinely open-ended
            # past question ("tell me something important that happened in
            # my past") has no explicit anchor for resolve_past_reference to
            # latch onto, so this branch used to simply do nothing — no
            # engine call, no candidate, a generic reply with nothing
            # chart-specific to say. Reuses the SAME past-direction engine
            # calls already used for explicit timing questions (no new
            # engine code) across career + marriage, prefers a candidate
            # within the recent-past horizon below (age-aware: never older
            # than the user's own birth year) over an old/childhood one, and
            # surfaces it as a specific, falsifiable candidate to ask about
            # — never as a stated fact.
            candidate = await _recent_past_candidate(db, profile, birth, body.language)
            if candidate is not None:
                context["past_event_candidate"] = candidate
                # The actual PredictionFeedback row is created further down,
                # AFTER the interpreter has generated its real reply — the
                # question the user actually sees is the LLM's own phrasing
                # of this candidate, not `candidate["reason"]` (the engine's
                # internal astrological justification, which reads nothing
                # like a question and badly confused classify_message's
                # later "is this message answering that" check when it was
                # stored as question_asked instead).
                pending_past_event_candidate = candidate

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
    # Structured facts remembered about this user from earlier conversations
    # (any Rishi) — see app.services.life_context_service — scoped to just
    # the domains relevant to what was actually asked (never the user's
    # entire life context on every turn), for personalization; never
    # treated as ground truth for the chart itself, and each fact still
    # carries its own confidence/source so the model can tell a stated fact
    # from its own earlier guess.
    # Fresh scoped context already includes this turn's structured writes.
    # Retrieval remains local unless semantic augmentation is explicitly enabled.
    # Caught live: a message from literally the immediately preceding turn
    # (seconds old) got surfaced as "in an earlier related conversation you
    # said..." — technically true (it IS earlier than this exact message)
    # but absurd to a real person, since nothing about "earlier" should mean
    # "just now". The last couple of the user's own turns in THIS
    # conversation are never quote candidates, on top of the existing
    # already-surfaced exclusion.
    recent_own_turn_ids = {row.id for row in history_rows[-2:] if row.role == "user"}
    context["retrieved_history"] = await chat_memory_service.retrieve_native_turns(
        db, user.id, categories, body.message,
        exclude_ids=set(conversation_state.get("surfaced_quote_ids", [])) | recent_own_turn_ids,
    )
    if not body.engine_only and get_settings().chat_semantic_memory_enabled:
        semantic = await chat_memory_service.retrieve_relevant_turns(
            db, user.id, body.rishi_id, body.message,
            exclude_ids_below=min(r.id for r in history_rows) if len(history_rows) >= _HISTORY_LIMIT else 0,
        )
        context["retrieved_history"].extend(semantic)
    if categories != ["memory_recall"]:
        dismissed = conversation_state.get("dismissed_memory_values", [])
        context["retrieved_history"] = [] if conversation_state.get("focus_confirmed") else [
            quote for quote in context["retrieved_history"]
            if not any(value.casefold() in quote.get("text", "").casefold() for value in dismissed)
        ]
    native_reply = await native_response.compose(history, context, body.language)
    reply = await chat_beautifier.beautify(native_reply, body.language, body.engine_only)
    # Product spec fix — a past QUESTION is filtered out of retrieved_history
    # entirely (see retrieve_native_turns), so anything that survives here
    # with source "user_quote" is a genuine stated fact native_response.
    # compose's "if that situation has changed" callback was actually able
    # to surface (same personal_context() gate compose() itself uses — see
    # that function's own docstring for why a historical quote is only
    # shown when nothing more current already personalized this reply).
    # Marking it surfaced stops the SAME callback repeating every turn the
    # topic recurs, and tracking it as pending lets a bare "yes"/"no" reply
    # actually be understood next turn (see conversation_engine.resume).
    retrieved_history = context.get("retrieved_history") or []
    if retrieved_history and retrieved_history[0].get("source") == "user_quote" and not native_response.personal_context(context, body.language):
        quote_id = retrieved_history[0]["id"]
        surfaced = set(conversation_state.get("surfaced_quote_ids", []))
        surfaced.add(quote_id)
        conversation_state["surfaced_quote_ids"] = list(surfaced)
        conversation_state["pending_situation_check"] = {"quote_id": quote_id}
        await conversation_engine.save_state(db, user.id, body.rishi_id, conversation_state)
    # Product spec §15/§30 — tracked using the REPLY THAT WAS ACTUALLY
    # SHOWN (truncated) as question_asked, not the engine's internal
    # reason text — that's what a later classify_message call needs to
    # recognize a reply as answering "the thing chat.py asked", since it's
    # what actually appears as the assistant's last turn in history.
    if pending_past_event_candidate is not None:
        candidate = pending_past_event_candidate
        await prediction_feedback_service.create_pending_feedback(
            db, user.id, "+".join(candidate["domains"]),
            datetime.combine(date.fromisoformat(candidate["start_date"]), datetime.min.time(), tzinfo=timezone.utc),
            datetime.combine(date.fromisoformat(candidate["end_date"]), datetime.min.time(), tzinfo=timezone.utc),
            reply[:2000],
        )
    # Which real specialist "owns" this question's topic — computed
    # independently of which persona actually answered (see
    # detect_answering_rishi), so it's a stable attribution label even when
    # the generalist "vyasa" persona is the one chatting.
    answered_by_rishi_id = detect_answering_rishi(body.message, birth.date_of_birth.year)
    # Context Utilization metric (product spec §20, see
    # app.services.metrics_service) — did real personal facts actually sit
    # on the table for THIS answer, not just "does personalization exist
    # anywhere in the system."
    used_personalization = bool(
        context["life_context"] or context["open_decisions"] or context["retrieved_history"]
    )
    # Phase 15 — Response Quality Validation, deliberately passive (logging
    # only, never gating what's returned): a hard gate risks silently
    # dropping a valid reply on a scoring false-negative, so this is
    # visibility for you to review, not a filter.
    logger.info(
        "chat_reply_quality",
        extra={
            "user_id": user.id,
            "rishi_id": body.rishi_id,
            "categories": categories,
            "used_personalization": used_personalization,
            "included_followup": "?" in reply,
            "rendered_technical_detail": wants_technical_detail(body.message),
        },
    )
    _log_reasoning(
        user_id=user.id, rishi_id=body.rishi_id, message=body.message, detected_intent=categories,
        life_state=context["life_state"], life_context=context["life_context"],
        response_type="native_styled" if reply != native_reply else "native",
        selected_interpretation=categories, previous_intent=previous_intent,
        used_intent_rescue=used_intent_rescue,
    )

    # Embeds THIS turn for future retrieval (see chat_memory_service) — a
    # pure enhancement, never allowed to affect the reply that's about to
    # be persisted: on any failure (quota, network) embed_turn returns
    # None and the row's embedding/embedding_source_text just stay NULL,
    # same "enhancement, not a hard dependency" convention as voice STT/TTS.
    embedded_turn = None
    if not body.engine_only and get_settings().chat_semantic_memory_enabled:
        embedded_turn = await chat_memory_service.embed_turn(body.message, reply)

    db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
    db.add(ChatMessage(
        user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id,
        used_personalization=used_personalization,
        embedding=json.dumps(embedded_turn[0]) if embedded_turn else None,
        embedding_source_text=embedded_turn[1] if embedded_turn else None,
    ))
    await db.commit()

    return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=answered_by_rishi_id,
                          question_type=context["question_type"],
                          response_source="native_styled" if reply != native_reply else "native")
