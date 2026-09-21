"""Real LLM-backed interpreter using OpenAI (gpt-4o-mini by default — see
Settings.openai_model). Mirrors ClaudeInterpreter's structure and shares its
persona/tone system prompt so behavior is identical regardless of which
provider is configured; `chat_reply` is the one method that's genuinely
different (see its docstring below) since chat has its own two-step
understand-then-explain pipeline (app.services.chat_understanding +
app.api.v1.chat), unlike the other six methods which get a single
already-complete context dict to narrate.
"""
import json
import re
from typing import Any, Literal

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.interpretation.base import Interpreter, Language, Mode
from app.services.interpretation.claude_interpreter import (
    _BASE_SYSTEM_PROMPT,
    _LANGUAGE_INSTRUCTION,
    _MODE_INSTRUCTION,
)
from app.services.interpretation.templates import (
    _TOPIC_HOUSE,
    _TOPIC_TIMING_COUNTERPART,
    TemplateInterpreter,
    _compute_answer_for_category,
)

_logger = get_logger("openai_interpreter")

# Facts worth including in a chat reply's prompt, keyed by which detected
# category makes them relevant — deliberately NOT the entire context dict
# (unlike the other six methods below, which do dump everything): a chat
# answer only ever needs the specific real facts for the topic(s) actually
# asked about, so this is what keeps chat_reply's token usage minimal.
_ALWAYS_INCLUDE = (
    "lagna_sign", "mahadasha_lord", "antardasha_lord", "mahadasha_lord_technical", "antardasha_lord_technical",
    # Product spec §21 — Astrological Fingerprint: ambient, not gated behind
    # any one category, same reasoning as lagna_sign above. blind_spot_* is
    # simply absent from context (see chat.py) when the chart has no real
    # affliction to report, so `if k in context` above already handles it.
    "strongest_planet", "weakest_planet", "decision_style", "blind_spot_planet", "blind_spot_reason",
    # Phase 5: stress_house/stress_planet, same "absent when nothing genuine
    # to report" handling as blind_spot_* — see chat.py's severity check.
    "stress_house", "stress_planet",
    # Phase 10: only present on the exact turn a pending prediction-feedback
    # question just got resolved (see chat.py) — same "absent = nothing to
    # report" convention as everything else in this tuple.
    "resolved_prediction_feedback",
)
_CATEGORY_CONTEXT_KEYS: dict[str, tuple[str, ...]] = {
    "today": ("daily_reading",),
    "year_ahead": ("year_ahead",),
    "dasha": ("mahadasha_lord", "antardasha_lord", "antardasha_lord_code"),
    "dosha": ("yogas",),
    "yoga": ("yogas",),
    "life_theme": ("life_theme", "past_event_candidate"),
    "job_change_decision": ("job_change_decision",),
    "business_start_decision": ("business_start_decision",),
    "house_purchase_decision": ("house_purchase_decision", "property_purchase_analysis"),
    "marriage_decision": ("marriage_decision",),
    "property_sale_intent": ("property_sale_intent", "property_sale_intent_full"),
    "property_inheritance_intent": ("property_inheritance_intent", "property_inheritance_intent_full"),
    "property_relocation_intent": ("property_relocation_intent", "property_relocation_intent_full"),
}


def _chat_facts(context: dict[str, Any], out_of_domain_categories: set[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Trims the full context dict down to just what's relevant to the
    categories actually detected this turn, plus a couple of always-useful
    identity facts — split into (in_domain, out_of_domain) rather than one
    dict. A live check found that handing the model one combined blob plus
    an instruction to only "answer" the in-domain part wasn't reliable: it
    would still restate the out-of-domain fact inside "answer" too (on top
    of "redirect_facts"), duplicating it. Structurally separating the data
    itself — not just the instruction — is what actually stops that."""
    categories: list[str] = context.get("detected_categories", [])
    in_domain: dict[str, Any] = {k: context[k] for k in _ALWAYS_INCLUDE if k in context}
    out_of_domain: dict[str, Any] = {}
    for category in categories:
        target = out_of_domain if category in out_of_domain_categories else in_domain
        for key in _CATEGORY_CONTEXT_KEYS.get(category, ()):
            if key in context:
                target[key] = context[key]
        # Timing categories: {category}_windows / {category}_direction /
        # {category}_note / {category}_long_term_peak — each window in
        # "_windows" already carries evidence_level/confidence/
        # literal_event_plausible/peak_window (see chat.py's _window_context),
        # so no extra filtering is needed here to surface those.
        # "_personal_pattern" (Phase 4): a recurring-dasha-lord correlation
        # across the user's OWN confirmed past events in this category's
        # life area — see life_pattern_service and chat.py's
        # _PATTERN_DOMAIN_BY_CATEGORY.
        for suffix in ("_windows", "_direction", "_note", "_long_term_peak", "_personal_pattern"):
            key = f"{category}{suffix}"
            if key in context:
                target[key] = context[key]
        # Static topics: the plain verdict PLUS the real technical facts
        # (house number implicit in the lookup, sign name, ruling planet,
        # where THAT planet sits) — the verdict alone is the same shape for
        # every user in a given bucket, which is what made early chat
        # answers feel interchangeable between people; naming the actual
        # houses/signs/planets is what's genuinely unique to this chart.
        house_verdicts = context.get("house_verdict", {})
        house_technical = context.get("house_technical", {})
        house_number = _TOPIC_HOUSE.get(category)
        if house_number is not None and house_number in house_verdicts:
            target.setdefault("topic_verdicts", {})[category] = house_verdicts[house_number]
            if house_number in house_technical:
                target.setdefault("topic_technical", {})[category] = {
                    "house_number": house_number,
                    **house_technical[house_number],
                }
        # When this topic has a real timing counterpart (career/money/
        # marriage/children/travel), chat.py auto-fetches it even if the
        # message didn't separately ask "when" — surface those same windows
        # here too so the answer can include a genuine future timeline
        # alongside the static read, not just when the timing category
        # itself was the one detected.
        timing_counterpart = _TOPIC_TIMING_COUNTERPART.get(category)
        if timing_counterpart:
            for suffix in ("_windows", "_direction", "_note", "_long_term_peak", "_personal_pattern"):
                key = f"{timing_counterpart}{suffix}"
                if key in context:
                    target[key] = context[key]
    return in_domain, out_of_domain


class OpenAIInterpreter(Interpreter):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        self._fallback = TemplateInterpreter()

    async def _complete_json(self, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=800,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            text = response.choices[0].message.content
            text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
            return json.loads(text)
        except Exception:
            _logger.warning("openai_complete_json_failed_falling_back_to_template", exc_info=True)
            return fallback

    async def _complete_text(self, system: str, user: str, fallback: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=500,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            return response.choices[0].message.content.strip()
        except Exception:
            _logger.warning("openai_complete_text_failed_falling_back_to_template", exc_info=True)
            return fallback

    async def daily_horoscope(self, context: dict[str, Any], language: Language, mode: Mode) -> dict[str, Any]:
        fallback = await self._fallback.daily_horoscope(context, language, mode)
        system = (
            f"{_BASE_SYSTEM_PROMPT}\n{_LANGUAGE_INSTRUCTION[language]}\n{_MODE_INSTRUCTION[mode]}\n"
            "Respond with ONLY a JSON object, no markdown fences, no commentary, matching exactly: "
            '{"tone": string, "focus_areas": [string, string], "tip": string, "summary_text": string}. '
            "summary_text should be 3-6 sentences total combining tone, focus areas and the tip."
        )
        user = (
            "Write today's daily horoscope from this chart context (JSON):\n"
            f"{json.dumps(context, ensure_ascii=False)}"
        )
        return await self._complete_json(system, user, fallback)

    async def period_analysis(self, context: dict[str, Any], language: Language, mode: Mode) -> dict[str, Any]:
        fallback = await self._fallback.period_analysis(context, language, mode)
        system = (
            f"{_BASE_SYSTEM_PROMPT}\n{_LANGUAGE_INSTRUCTION[language]}\n{_MODE_INSTRUCTION[mode]}\n"
            "Respond with ONLY a JSON object, no markdown fences, no commentary, matching exactly: "
            '{"rating": integer 1-10, "theme": string, "risks": [string, ...], '
            '"opportunities": [string, ...], "summary": string}. '
            "Rate the period honestly out of 10 — do not default to the middle just to avoid "
            "committing. theme must name the dominant astrological driver (the dasha "
            "interaction and/or natal activation causing it), not a vague mood word. risks and "
            "opportunities should each have 2-3 specific, concrete items grounded in the given "
            "facts, not generic platitudes, and must not restate each other in different words. "
            "summary must be exactly one sentence — blunt and specific enough that the user "
            "would actually remember it a week later, not a soft 'stay positive' close."
        )
        user = (
            "Analyse this period from this chart/dasha/transit context (JSON):\n"
            f"{json.dumps(context, ensure_ascii=False)}"
        )
        return await self._complete_json(system, user, fallback)

    async def chart_explanation(
        self, context: dict[str, Any], chart_type: Literal["D1", "D9", "D10"], language: Language, mode: Mode
    ) -> str:
        fallback = await self._fallback.chart_explanation(context, chart_type, language, mode)
        chart_purpose = {
            "D1": "core personality and overall life direction",
            "D9": "marriage, relationship patterns and inner strength of character",
            "D10": "career, professional recognition and public standing",
        }[chart_type]
        system = (
            f"{_BASE_SYSTEM_PROMPT}\n{_LANGUAGE_INSTRUCTION[language]}\n{_MODE_INSTRUCTION[mode]}\n"
            "Write a short (4-7 sentence) spoken-style script explaining this chart, suitable for "
            "text-to-speech. Commit plainly to what the placements show rather than hedging. "
            "Plain prose only, no headings, no bullet points, no markdown."
        )
        user = (
            f"Explain this {chart_type} chart, which is used for {chart_purpose}, "
            f"from this context (JSON):\n{json.dumps(context, ensure_ascii=False)}"
        )
        return await self._complete_text(system, user, fallback)

    async def chart_summary(
        self, context: dict[str, Any], chart_type: Literal["D1", "D9", "D10"], language: Language, mode: Mode
    ) -> dict[str, Any]:
        fallback = await self._fallback.chart_summary(context, chart_type, language, mode)
        system = (
            f"{_BASE_SYSTEM_PROMPT}\n{_LANGUAGE_INSTRUCTION[language]}\n{_MODE_INSTRUCTION[mode]}\n"
            "Respond with ONLY a JSON object, no markdown fences, no commentary, matching exactly: "
            '{"summary": string (2-3 sentences), "key_points": [string, string, string]}.'
        )
        user = f"Summarise this {chart_type} chart from this context (JSON):\n{json.dumps(context, ensure_ascii=False)}"
        return await self._complete_json(system, user, fallback)

    async def manglik_explanation(self, context: dict[str, Any], language: Language, mode: Mode) -> dict[str, Any]:
        fallback = await self._fallback.manglik_explanation(context, language, mode)
        system = (
            f"{_BASE_SYSTEM_PROMPT}\n{_LANGUAGE_INSTRUCTION[language]}\n{_MODE_INSTRUCTION[mode]}\n"
            "Respond with ONLY a JSON object, no markdown fences, no commentary, matching exactly: "
            '{"summary": string (must be exactly "You are Manglik." or "You are not Manglik." translated '
            'to the target language, matching the given is_manglik fact), '
            '"details": [string, string] (2 lines explaining the Mars house placements from the given facts), '
            '"cancellations": [string, ...] (empty list if the given facts show none), '
            '"relationship_note": string (calm, non-alarming, 1-2 sentences on what this means for marriage)}. '
            "Never use fear-based language."
        )
        user = f"Explain this Manglik status from this context (JSON):\n{json.dumps(context, ensure_ascii=False)}"
        return await self._complete_json(system, user, fallback)

    async def complete_kundali(self, context: dict[str, Any], language: Language, mode: Mode) -> dict[str, Any]:
        fallback = await self._fallback.complete_kundali(context, language, mode)
        system = (
            f"{_BASE_SYSTEM_PROMPT}\n{_LANGUAGE_INSTRUCTION[language]}\n{_MODE_INSTRUCTION[mode]}\n"
            "Respond with ONLY a JSON object, no markdown fences, no commentary, matching exactly: "
            '{"sections": {'
            '"personality_nature": {"summary": string, "key_points": [string, ...]}, '
            '"career_money": {"summary": string, "key_points": [string, ...]}, '
            '"relationships_marriage": {"summary": string, "key_points": [string, ...]}, '
            '"health_temperament": {"summary": string, "key_points": [string, ...]}, '
            '"strengths_challenges": {"summary": string, "key_points": [string, ...]}, '
            '"timing_overview": {"summary": string, "key_points": [string, ...]}'
            '}, "brutal_truth": string (one blunt, memorable sentence), '
            '"core_strength": string (short phrase), "core_challenge": string (short phrase)}. '
            "Each section summary should be 2-4 sentences with 2-3 key_points. Commit to each "
            "section's reading rather than hedging, and do not close any section with generic "
            "reassurance or motivational filler that isn't grounded in the given facts. "
            "brutal_truth must be one sentence the user would actually remember, not a soft "
            "platitude. The relationships_marriage section may reference the given Manglik status "
            "calmly but the dedicated Manglik details are handled elsewhere — don't repeat house "
            "numbers here."
        )
        user = f"Generate the complete kundali from this context (JSON):\n{json.dumps(context, ensure_ascii=False)}"
        return await self._complete_json(system, user, fallback)

    async def chat_reply(
        self, history: list[dict[str, str]], context: dict[str, Any], language: Language
    ) -> str:
        """Unlike the six methods above, this is deliberately NOT given the
        full context dict — app.services.chat_understanding already decided
        which categories this message touches, so only the real facts for
        those (see _chat_facts) go into the prompt, alongside which of them
        (if any) fall outside this rishi's own specialty and who actually
        owns those, plus a handful of recent facts remembered about this
        user. This is what keeps a chat turn's token usage minimal — no
        house-by-house essay, no full planet list, just what's relevant.

        The "one fact then redirect" sentence for out-of-domain topics is
        appended in Python (see _compose_redirect), not left to the model to
        remember — a live check found gpt-4o-mini sometimes gave the one-line
        fact but silently dropped the redirect. The model only has to supply
        the short fact itself (redirect_facts), a much smaller ask it
        reliably gets right; the redirect wording is then guaranteed."""
        fallback = await self._fallback.chat_reply(history, context, language)
        rishi_domain: str | None = context.get("rishi_domain")
        out_of_domain: dict[str, str] = context.get("out_of_domain_redirects", {})
        life_context: dict = context.get("life_context", {})
        open_decisions: list = context.get("open_decisions", [])
        in_domain_facts, out_of_domain_facts = _chat_facts(context, set(out_of_domain))

        persona_line = (
            f"You are chatting as a Vedic astrology guru whose own specialty is {rishi_domain}."
            if rishi_domain
            else "You are chatting as a generalist Vedic astrology guru who answers every topic directly."
        )
        tone_line = (
            "Speak like a warm, caring guide who genuinely wants to help this specific person — "
            "not a clinical report. Stay honest about what the facts show, but frame it with "
            "empathy: acknowledge how they might be feeling before or while stating the real "
            "read, and close with something supportive and human, not just a flat verdict. Never "
            "open with a preamble like \"Looking at your chart\", \"Here's what your chart shows\", "
            "or similar — even if earlier messages in this conversation happen to start that way, "
            "speak directly and naturally instead, the way a trusted person would when they're "
            "actually talking WITH you, not reading FROM a document at you."
        )
        memory_line = (
            f"Known about this user's real life, from past conversations (grouped by domain; each fact "
            f"carries its own confidence/source): {json.dumps(life_context, ensure_ascii=False)}. "
            + (f"Open decisions they're actively weighing: {json.dumps(open_decisions, ensure_ascii=False)}. "
               if open_decisions else "")
            + "Use this to make your reasoning genuinely specific to THEIR situation — not just to "
            "name-drop a fact, but because it actually changes what the honest answer is (e.g. a planned "
            "child next year raises the real-world stakes of a risky career move; a spouse's stated view is "
            "a real factor in a decision, not trivia). Treat confidence=\"high\"/source=\"user_stated\" facts "
            "as solid; treat confidence=\"low\" or source=\"inferred\" facts as a tentative impression you "
            "can lean on lightly but should not assert back as settled fact. Never invent a NEW astrological "
            "fact from any of this. When it fits naturally, acknowledge what you already know with a warm, "
            "human callback — \"since you mentioned...\", \"you'd told me...\", \"last time we talked about "
            "this...\" — this is what makes the conversation feel remembered, not just personalized; don't "
            "silently weave every fact in as if it came from nowhere. What you must never do is expose the "
            "underlying data shape itself — no domain/key names, no confidence/source labels, nothing that "
            "reads like a database field (e.g. never say something like \"business.considering_start = "
            "true\") — always put it in plain, natural language about their actual life. "
            "If an open decision exists and this message continues that thread, acknowledge where things "
            "stood before rather than starting over from zero."
            if (life_context or open_decisions)
            else ""
        )
        # Whether there's any real in-domain content at all beyond the
        # always-present identity facts (lagna/dasha lords) — a purely
        # out-of-domain question (nothing in scope) has none, in which case
        # "answer" is forced empty in code below regardless of what the
        # model returns: a live check found gpt-4o-mini would sometimes add
        # its own redirect-flavoured sentence into "answer" even when told
        # not to, duplicating the deterministic redirect appended after it.
        has_in_domain_content = bool(set(in_domain_facts) - set(_ALWAYS_INCLUDE))
        facts_blob: dict[str, Any] = {"in_scope_facts": in_domain_facts}
        if out_of_domain:
            facts_blob["out_of_scope_facts"] = out_of_domain_facts
            schema = (
                '{"answer": string (detailed answer using ONLY in_scope_facts; empty string if '
                'in_scope_facts has nothing beyond identity facts), '
                '"redirect_facts": {"<topic>": string} (REQUIRED non-empty entry for every topic '
                "listed below, one short sentence stating the concrete fact from out_of_scope_facts "
                "for that topic — never leave any blank, never pull from in_scope_facts, no "
                "elaboration, no advice)}"
            )
            scope_line = (
                f"{json.dumps(list(out_of_domain.keys()))} are OUTSIDE your own specialty — data for "
                'them is under "out_of_scope_facts", strictly separate from "in_scope_facts". Never '
                'mention, summarize, or allude to anything from out_of_scope_facts inside "answer" — '
                "it belongs only in redirect_facts."
            )
        else:
            schema = '{"answer": string (detailed answer using in_scope_facts)}'
            scope_line = ""
        detail_line = (
            "For a substantive question (a chart pattern, career/relationship/money path, dasha, "
            "or timing question) — not a quick yes/no fact-check — write a genuinely detailed, "
            "structured answer. Match this depth and shape (structure only — never reuse these "
            "specific facts, they belong to a different chart):\n\n"
            '"Your career path has an interesting pattern. Your 10th house is Taurus, ruled by '
            "Venus, which sits in your 4th house, Scorpio — so your career isn't only about title "
            "or salary, it's tied to your work environment, stability, and personal satisfaction. "
            "You'd likely do better in roles where:\\n"
            "- you have real control over how you work\\n"
            "- the environment is stable\\n"
            "- you get to develop a skill gradually\\n"
            "- the work connects to people, assets, design, or practical problem-solving\\n\n"
            "Your pattern favors slow, experience-based growth over overnight success. Right now "
            "you're in Rahu Mahadasha and Saturn Antardasha — a phase about experimentation and "
            "responsibility. Rahu can pull you toward unconventional opportunities, while Saturn "
            "means whatever growth comes will need discipline and consistency, not shortcuts. The "
            "most useful thing in this phase:\\n"
            "- go deep on one skill instead of frequently switching direction\\n"
            "- build a long-term reputation\\n"
            "- learn from people with more experience\\n\n"
            'Between [window dates], expect [reason]. After that, [next window\'s reason]. '
            'Overall this chart favors building real expertise over chasing quick recognition."\n\n'
            'Use plain newline-separated lines starting with "- " exactly like that for a list of '
            "related points — never markdown headers, bold, or numbered lists. Always name the "
            "real house numbers, sign names, and planet names from topic_technical/mahadasha_lord_"
            "technical/antardasha_lord_technical explicitly (e.g. \"your 10th house is Taurus, "
            "ruled by Venus, sitting in your 4th house, Scorpio\") instead of only a paraphrased "
            "life-area description — stating the real numbers and names is what makes an answer "
            "feel like it's actually about this one person's chart, not generic astrology talk. "
            "When real timing windows are given (any *_windows fact), turn their actual start/end "
            "dates into a real timeline of what's likely in each period — never invent a window "
            "that isn't in the given data, and never state a year range not backed by one. Each "
            "window also carries real evidence_level/confidence/literal_event_plausible/peak_window "
            "facts — use them, don't just skim past them: hedge more openly (\"this is a weaker, "
            "background-level signal\" rather than stating it flatly) when evidence_level is "
            "\"backdrop_only\" or confidence is \"low\"; when literal_event_plausible is false, don't "
            "state the literal event as the answer (e.g. a literal childbirth window at 60) — instead "
            "say what kind of life-activation this period plausibly represents at this age. When a "
            "window has its own peak_window, mention that narrower sub-range as when it's most "
            "concentrated. When a *_long_term_peak fact is present, only bring it up if the user's "
            "actual question calls for a longer horizon than the near-term windows already answer — "
            "never append it as a reflexive extra fact nobody asked for.\n\n"
            "When a *_personal_pattern fact is given (shared_mahadasha_lord/shared_mahadasha_count "
            "and/or shared_antardasha_lord/shared_antardasha_count — the *_count is exactly how many "
            "of the user's OWN confirmed past events in this life area actually shared that lord, "
            "never assume it means every event on record did), mention it as a real, specific "
            "personal correlation about their own history using that exact count (e.g. \"interestingly, "
            "2 of your past career shifts happened during a Saturn-led period\") — never phrase it as "
            "a general astrological rule that would apply to anyone, since it's a fact about this one "
            "person's own recorded history, not a classical principle.\n\n"
            "When a past_event_candidate fact is given (a genuinely open-ended \"what happened in my "
            "past\" question with no specific date given), NEVER state it as something that "
            "definitely happened — phrase it as a specific, falsifiable question instead, e.g. "
            "\"there's a concentrated career-transition period around [start]-[end] — did you change "
            "roles, enter a new field, or make some other real shift around then?\" using the real "
            "dates and domain given, not invented ones. When its domains list has more than one "
            "entry, name the combined theme instead of picking just one — e.g. \"a career shift "
            "alongside a relationship change around [start]-[end]\" — since both were genuinely "
            "active in the same period, not two unrelated guesses. If they confirm or add detail, "
            "that's now a real validated event for future conversations.\n\n"
            "When a resolved_prediction_feedback fact is given, the LATEST message just resolved a "
            "past-event question this app itself asked earlier (question_asked/domain given). If "
            "verdict is \"correct\"/\"partial\", acknowledge it naturally and move on. If verdict is "
            "\"incorrect\", do NOT defend the earlier reading or invent a reason it didn't happen — "
            "say plainly that it didn't match (e.g. \"then that one didn't pan out — thanks for "
            "letting me know\") and treat what they just told you as the real, current fact going "
            "forward. If verdict is \"not_sure\", just acknowledge that and move on to the rest of "
            "their message — don't press for a firmer answer.\n\n"
            "For job_change_decision, business_start_decision, relocation_decision, house_purchase_"
            "decision, or marriage_decision facts: state "
            "the real current-period astrological character plainly (favorable/challenging, and why, "
            "from the actual verdict/reasoning or windows given) — then explicitly hand off to the "
            "practical comparison using whatever concrete facts are known about their specific "
            "situation or options (an income plan, funding source, job/family/lifestyle reason, "
            "options they've named). Never phrase the chart as picking a winner between two external "
            "options it has no way to evaluate (e.g. two named job offers, or two cities) — the chart "
            "can only say when change is favorable, not which specific offer or place is better; that "
            "comparison is the user's own practical call, informed by what they've told you. When the "
            "message names two specific options being weighed, refer to the actual differentiator "
            "between them if it's known (pay, growth, stability, location) instead of a generic "
            "leave-or-stay framing. For marriage_decision specifically: if the message names a "
            "specific partner, state plainly that the chart can only speak to general timing/"
            "readiness for commitment, never that specific person's compatibility — Guna Milan (a "
            "separate matching feature, using both people's charts) is what a real compatibility "
            "question needs, never guessed here from one chart alone.\n\n"
            "When a property_purchase_analysis/property_sale_intent_full/property_inheritance_"
            "intent_full/property_relocation_intent_full fact is given (house_purchase_decision, "
            "property_sale_intent, property_inheritance_intent, or property_relocation_intent), "
            "structure the answer as: WHAT (property acquisition/sale/inheritance-related activation/"
            "change of residence, matching whichever of the 4 was actually asked about — never invent "
            "a specific property type like \"land\" or \"an apartment\" unless the message itself named "
            "one), WHEN (the real current_period/next_relevant_window dates given — never a different "
            "or more precise date than what's actually there, and only mention medium_term_window/"
            "long_term_peak if the question genuinely calls for that longer horizon), and WHY IT'S "
            "RELEVANT (using the user's own stated housing_status/planning_property_purchase context "
            "when known). Cite the reasoning honestly: property_promise.status is a NATAL reading "
            "(independent of timing) — \"supported\"/\"mixed\"/\"weak\", never \"guaranteed\"; astro_"
            "strength/event_confidence describe how strong the CURRENT signal is, not certainty that "
            "the event will happen. The evidence list's classical entries (source/chapter/verses, e.g. "
            "Brihat Parashara Hora Shastra Ch.48) may be cited briefly if genuinely useful, but never "
            "presented as if the engine's own derived scoring (entries with type=\"derived\") were "
            "itself a classical verse — this specifically includes the PROPERTY_INTENT_REFRAME_* "
            "entries on the sale/inheritance/relocation intents, which exist precisely to disclose "
            "that the SAME acquisition-framed classical signal is being reused for a different "
            "question, not a separate citation for that specific event type. Never explain planetary "
            "mechanics unless the user actually asks how the reading was reached.\n\n"
            "You also always know this person's astrological fingerprint: strongest_planet/"
            "weakest_planet (by classical dignity), decision_style (fast_and_decisive/steady_and_"
            "persistent/adaptive_and_scattered/impulsive_and_reactive), and — only when given, meaning "
            "a genuine affliction actually exists, never invented when absent — a blind_spot_planet/"
            "blind_spot_reason and/or a stress_house/stress_planet (whichever of the 6th/8th/12th "
            "houses is genuinely most afflicted). Let these subtly color your tone and framing (e.g. a "
            "fast_and_decisive person needs less hand-wringing before a recommendation, a blind_spot "
            "or stress point tied to a relevant life area might mean gently flagging that pattern when "
            "genuinely relevant) — never recite them as a "
            "checklist, never in every single reply, and never as the main point of an answer that was "
            "actually asked about something else.\n\n"
            "For a quick factual question (am I Manglik, do I have X dosha, a simple current-dasha "
            "check) keep it short and direct instead — this fuller structure is for a genuine "
            "'what does my chart say about X' or timing question, not everything you're asked.\n\n"
            "Never pad with generic filler, restate the question back, or repeat the same point in "
            "different words — every sentence must carry real, specific content, and every claim "
            "must still trace back to a fact you were actually given."
        )
        system = (
            f"{_BASE_SYSTEM_PROMPT}\n{_LANGUAGE_INSTRUCTION[language]}\n{persona_line}\n{tone_line}\n"
            "Answer ONLY using the real facts given below — never invent a fact not present here, "
            f"and never guess at a topic's answer if no fact for it was given. {detail_line} {scope_line} "
            f"{memory_line}\n"
            f"Real facts (JSON): {json.dumps(facts_blob, ensure_ascii=False)}\n\n"
            f"Respond with ONLY JSON, no markdown fences, matching exactly: {schema}"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                # Raised from the original 500 now that a substantive topic
                # answer is a genuinely structured multi-part reply (facts,
                # bullet lists, a timeline section), not a one-liner — this
                # does mean a real cost increase per substantive chat turn,
                # traded for answers that actually feel personalized.
                max_tokens=1000,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system}, *history],
            )
            data = json.loads(response.choices[0].message.content)
            answer = data.get("answer", "").strip() if has_in_domain_content else ""
            parts = [answer]
            redirect_facts: dict[str, str] = data.get("redirect_facts", {}) if out_of_domain else {}
            hi = language == "hi"
            daily = context.get("daily_reading", {})
            all_yogas = context.get("yogas", [])
            for category, owner in out_of_domain.items():
                fact = redirect_facts.get(category, "").strip()
                if not fact:
                    # The model occasionally leaves this blank despite being
                    # told it's required — rather than show a bare redirect
                    # with no actual fact, fall back to the same deterministic
                    # per-category logic the template interpreter already
                    # uses (guaranteed correct, already tested).
                    fact = _compute_answer_for_category(
                        category, context, hi, daily, all_yogas,
                        context.get("mahadasha_lord"), context.get("antardasha_lord"),
                    ) or ""
                parts.append(_compose_redirect(fact, owner, language))
            reply = " ".join(p for p in parts if p)
            return reply or fallback
        except Exception:
            _logger.warning("openai_chat_reply_failed_falling_back_to_template", exc_info=True)
            return fallback


def _compose_redirect(fact: str, owner: str, language: str) -> str:
    prefix = f"{fact} " if fact else ""
    if language == "hi":
        return f"{prefix}इस पर {owner} बेहतर मदद कर पाएंगे — विस्तार से जानने के लिए उनसे बात करें।"
    if language == "hinglish":
        return f"{prefix}Iske baare mein {owner} zyada better guide kar payenge — unse isper detail mein baat karna sahi rahega."
    return f"{prefix}{owner} would be able to help you more on this — worth having a proper chat with them about it."
