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
from app.services import life_context_service, prediction_service, user_service
from app.services.chart_service import get_chart
from app.services.chat_understanding import classify_message, compute_out_of_domain_redirects, relevant_domains
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


_DECISION_LABEL_EN = {"job_change": "leaving your job", "business_start": "starting your business"}
_DECISION_LABEL_HI = {"job_change": "नौकरी छोड़ने", "business_start": "अपना व्यवसाय शुरू करने"}


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

    # Decides which real-life categories this message touches — an OpenAI
    # call when configured (see app.services.chat_understanding), otherwise
    # today's exact keyword-matching behaviour. Either way, this is the ONLY
    # thing that decides what to fetch below; the actual facts always come
    # from the real Prediction Engine calls that follow, never from the LLM.
    understanding = await classify_message(
        history, body.rishi_id, birth.date_of_birth.year, body.language,
        open_decisions_for_prompt, pending_checkins_for_prompt, pending_reconfirmation_for_prompt,
        decision_known_facts_for_prompt,
    )

    if understanding.needs_clarification and understanding.clarifying_question:
        # Too vague to answer honestly — ask instead of guessing. No engine
        # calls, no interpreter call: nothing to explain yet.
        reply = understanding.clarifying_question
        db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id))
        await db.commit()
        return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=None)

    # Product spec §7 — Decision-critical gap-filling: the message clearly
    # touches a decision (first time raised or already tracked — see
    # decision_known_facts_for_prompt above, fetched unconditionally for
    # both), but classify_message flagged that one fact materially needed
    # to give real advice isn't known yet — ask for exactly that, same
    # skip-the-engine-calls treatment as needs_clarification above, just a
    # narrower and more specific reason for asking instead of answering.
    if understanding.decision_gap_question and any(
        c in decision_known_facts_for_prompt for c in understanding.categories
    ):
        reply = understanding.decision_gap_question
        db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id))
        await db.commit()
        return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=None)

    categories = understanding.categories
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
            # Life Context's Decision Memory (see life_context_service) —
            # a separate, persistent object from the astrological verdict
            # above, so a LATER conversation can reference "last time you
            # were exploring this" instead of re-deriving it from scratch.
            await life_context_service.upsert_decision(db, user.id, category, body.message)

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
    # Structured facts remembered about this user from earlier conversations
    # (any Rishi) — see app.services.life_context_service — scoped to just
    # the domains relevant to what was actually asked (never the user's
    # entire life context on every turn), for personalization; never
    # treated as ground truth for the chart itself, and each fact still
    # carries its own confidence/source so the model can tell a stated fact
    # from its own earlier guess.
    context["life_context"] = await life_context_service.get_active_context(db, user.id, relevant_domains(categories))
    # Reuses the same open_decision_objs fetched earlier (for the classifier
    # prompt) rather than querying again — this list is small (at most one
    # per decision type) so no pagination/limit concern either way.
    context["open_decisions"] = [
        {"decision_type": d.decision_type, "context": d.context, "created_at": d.created_at.isoformat()}
        for d in open_decision_objs
        if d.decision_type in {dt for dt, cat in _DECISION_CHECKS if cat in categories}
    ]

    interpreter = get_interpreter()
    reply = await interpreter.chat_reply(history, context, body.language)
    # Which real specialist "owns" this question's topic — computed
    # independently of which persona actually answered (see
    # detect_answering_rishi), so it's a stable attribution label even when
    # the generalist "vyasa" persona is the one chatting.
    answered_by_rishi_id = detect_answering_rishi(body.message, birth.date_of_birth.year)
    # Context Utilization metric (product spec §20, see
    # app.services.metrics_service) — did real personal facts actually sit
    # on the table for THIS answer, not just "does personalization exist
    # anywhere in the system."
    used_personalization = bool(context["life_context"] or context["open_decisions"])

    db.add(ChatMessage(user_id=user.id, role="user", content=body.message, language=body.language, rishi_id=body.rishi_id))
    db.add(ChatMessage(
        user_id=user.id, role="assistant", content=reply, language=body.language, rishi_id=body.rishi_id,
        used_personalization=used_personalization,
    ))
    await db.commit()

    return ChatMessageOut(reply=reply, language=body.language, answered_by_rishi_id=answered_by_rishi_id)
