"""Prediction Engine: year-ahead / multi-year outlook (Varshaphala + running
dasha + transit doshas) and marriage-timing prediction (dasha/transit window
scan). Every fact here is computed from the person's real birth data — no
LLM call, no scraped/templated third-party content (see the Prediction
Engine plan). Both languages are computed and cached together, same
convention as every other cached artifact in this app.
"""
from datetime import date, datetime, timezone
from typing import Literal

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.charts import house_number, navamsa_sign_index, sign_index
from app.astro.constants import DAYS_PER_YEAR, PLANET_NAMES_EN, PLANET_NAMES_HI
from app.astro.dasha import Mahadasha, find_current_antardasha, find_current_mahadasha
from app.astro.doshas import compute_dhaiya, compute_sade_sati
from app.astro.ephemeris import all_planet_positions, ascendant_sidereal, declination, julian_day_ut
from app.astro.event_window_scanner import ScoredWindow
from app.astro.life_event_timing import EventType
from app.astro.life_event_timing import EVENT_HOUSE as LIFE_EVENT_HOUSE
from app.astro.life_event_timing import corroborate_with_transits as corroborate_life_event_with_transits
from app.astro.life_event_timing import find_event_windows
from app.astro.life_stage_plausibility import (
    EventCategory,
    age_plausibility_multiplier,
    is_hard_implausible_age,
    is_implausible_age,
)
from app.astro.manglik import compute_manglik_facts
from app.astro.marriage_timing import corroborate_with_transits, find_marriage_windows
from app.astro.natal_insights import (
    aspect_and_conjunction_multiplier,
    house_lord,
    planet_dignity,
    significator_strength_multipliers,
)
from app.astro.shadbala import MINIMUM_RUPAS, ShadbalaChartInputs, compute_all_shadbala, compute_time_of_day_facts
from app.astro.transit_corroboration import TransitCheck
from app.astro.transits import compute_transit_snapshot
from app.astro.varshaphala import compute_solar_return, compute_varshaphala
from app.astro.vargas import (
    drekkana_sign_index,
    dwadashamsa_sign_index,
    hora_sign_index,
    saptamsa_sign_index,
    trimshamsa_sign_index,
)
from app.db.models.birth_profile import BirthProfile
from app.db.models.cache import (
    LifeEventTimingCache,
    LifeThemeCache,
    MarriageTimingCache,
    SignificatorStrengthCache,
    YearOutlookCache,
)
from app.schemas.prediction import (
    LifeEventTimingResponse,
    LifeThemeResponse,
    MarriageTimingResponse,
    MultiYearOutlookResponse,
    YearOutlookResponse,
)
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_service import birth_datetime_utc, get_chart
from app.services.dasha_service import get_mahadashas_raw
from app.services.interpretation.base import Language
from app.services.interpretation.prediction_templates import (
    life_event_reason_text,
    life_theme_text,
    marriage_window_reason_text,
    overall_year_theme,
    year_outlook_text,
)

Direction = Literal["past", "future"]
_FUTURE_HORIZON_YEARS = 20.0

# Transit corroboration (Jupiter/Saturn transiting the event's own house
# during the window — the classical gochar confirmation) used to be purely
# cosmetic: computed, shown in the reason text, but never folded into the
# score used to RANK windows. That let a window scoring higher on dasha
# lordship alone (e.g. a lord's own Mahadasha AND Antardasha coinciding)
# outrank an earlier, transit-CONFIRMED window that only had a single
# antardasha-level signal — even though a real, independent transit
# confirmation is exactly the kind of corroborating signal a real
# astrologer weighs heavily. Caught by comparing a real chart's output
# against its own dasha timeline: the transit-corroborated window was
# sitting in 2nd place purely because corroboration wasn't scored.
#
# Scanning a wider candidate pool before corroborating (instead of only
# corroborating whatever already made the dasha-only top 3) means a
# transit-confirmed window further down the dasha-only ranking still gets a
# fair chance to surface once its corroboration bonus is applied.
_CANDIDATE_POOL_SIZE = 8
# How many raw, dasha-score-only windows to pull from the scanner (see
# app.astro.event_window_scanner.scan_dasha_windows, which itself returns
# every non-zero-scoring Antardasha in the horizon, already sorted) BEFORE
# picking the final _CANDIDATE_POOL_SIZE to run the more expensive transit
# corroboration on. Needs to be comfortably larger than _CANDIDATE_POOL_SIZE
# so _select_candidate_pool below actually has plausible-age alternatives to
# choose from — a full ~120-year Vimshottari cycle has at most 9 Mahadashas
# x 9 Antardashas = 81 windows total, so 60 comfortably covers even a
# past-direction search spanning most of a long life.
_RAW_SCAN_POOL_SIZE = 60
_FINAL_WINDOW_COUNT = 3
# Sized between the antardasha-level rule weights (2.0-3.0) and the
# mahadasha-level ones (0.5-1.0) — real, but not so large that
# corroboration alone can promote a window with a much weaker dasha signal
# above one with a strong one. Scaled per-window by the corroborating
# transit's own Ashtakavarga strength (see app.astro.transit_corroboration
# and app.astro.ashtakavarga) — a corroborating transit with weak Ashtakavarga
# support (0.5x) is worth much less than one with strong support (1.5x),
# instead of every corroborating transit counting identically.
_TRANSIT_CORROBORATION_BONUS = 1.5
# A DIFFERENT malefic obstructing (transiting or classically aspecting) the
# same house at the same time — see app.astro.transit_corroboration —
# subtracts this. Smaller than the strongest possible corroboration bonus
# (1.5 * 1.5 = 2.25) so a single obstruction can't single-handedly bury a
# strongly-corroborated window, but real enough to matter against a weak or
# absent corroboration.
_TRANSIT_OBSTRUCTION_PENALTY = 1.0

# Bump this whenever the window-scoring/ranking logic changes (like the
# transit-bonus fix above did) — the cache is keyed by (user, direction,
# language, birth_profile_version), none of which change when the CODE
# changes, so a previously-cached prediction would otherwise keep being
# served forever with the OLD ranking even after a real scoring fix ships.
# Caught live: a user re-tested right after the transit-bonus fix and still
# saw the old, wrong top window because their cache row predated it.
# v3: dasha rule weights are now scaled by each significator's real natal
# strength (dignity/dusthana/combustion — see
# app.astro.natal_insights.significator_strength_multipliers) instead of
# treating "whose dasha is it" as the only signal regardless of how well or
# badly placed that planet actually is in this chart.
# v4: window scores now also factor in whether the Antardasha lord is a
# natural friend/enemy of (or the same planet as) its Mahadasha lord — see
# app.astro.event_window_scanner's weigh_dasha_relationship — instead of
# judging the Antardasha lord's significations in isolation from the
# broader period it runs inside.
# v5: reason text now also NOTES (deliberately does not score — see
# _significator_retrograde below) whether the Antardasha lord is retrograde.
# v6: each significator's natal strength (see
# app.astro.natal_insights.significator_strength_multipliers) now also
# factors in classical Parashari aspects (drishti) AND conjunctions from
# every other planet in the chart — a benefic aspect/conjunction is real
# support, a malefic one a real affliction — instead of judging a
# significator's strength from its own sign/house placement alone.
# v7: transit corroboration is no longer a flat yes/no bonus — it's scaled
# by the corroborating transit's own Ashtakavarga (Bhinnashtakavarga)
# strength at the sign it's transiting (app.astro.ashtakavarga), and windows
# now also carry an independent transit-OBSTRUCTION penalty when a different
# malefic transits or classically aspects the same house at the same time
# (app.astro.transit_corroboration) — instead of every "the right planet
# transited the right house" being treated as equally, unconditionally good.
# v8: each significator's natal strength now ALSO factors in Vargottama
# (same sign in D1 and D9 — app.astro.natal_insights.vargottama_multiplier)
# and full Shadbala (app.astro.shadbala — all six classical strength limbs,
# not just the dignity/aspect/combustion approximation used until now).
# v9: three real-world gaps found by comparing this engine's output against
# independent chart reads across several real charts:
#   - windows now carry a real-world AGE-PLAUSIBILITY factor (see
#     app.astro.life_stage_plausibility) — without it, a chart's own
#     infancy could mathematically outrank a sensible-age window for
#     "career"/"children"/etc, because the very first Antardasha of any
#     life is structurally the strongest possible dasha-relationship
#     combination (same lord at both levels), which has nothing to do with
#     whether a newborn can plausibly have a career.
#   - the transit-obstruction penalty is now scaled by what FRACTION of the
#     sampled points show it (app.astro.transit_corroboration.TransitCheck.
#     obstruction_fraction), not a flat penalty for "happened at least
#     once" — empirically that bar was clearing on ~70% of windows across a
#     real multi-chart test, which stopped being a meaningful differentiator.
#   - a FUTURE search now starts from the true beginning of whichever
#     Antardasha is already running right now (see _search_bounds), instead
#     of clipping it to "now" — a currently-active strong window used to
#     only ever appear as a fragment of its real score in either direction.
# v10: karaka rule weights (marriage_rules/event_rules) are now scaled by
# app.astro.event_karakas.karaka_specificity_multiplier — Jupiter and Venus
# are each classical karakas for MULTIPLE categories (Jupiter: marriage,
# wealth, children, foreign_travel; Venus: marriage, wealth), so without
# this a single strong Jupiter/Venus Antardasha could win most categories
# at once from the identical real dasha window. Verified empirically: 78%
# of a 20-chart test's user/direction combinations shared a duplicate #1
# window across categories before this change.
# v11: age/event plausibility is now a real SELECTION constraint, not only a
# score multiplier — found by comparing this engine's output against
# independent chart reads: the v10 category-overlap fix made the engine
# correctly prefer a category's real house lord over a merely-shared
# karaka, but that exposed a NEW problem — a technically well-supported
# house-lord window at a hard-implausible age (e.g. personal "wealth" at
# 14, a literal "children" event at 63) could still win purely because its
# score, even multiplied down, still beat every other candidate. Two
# changes fix this:
#   - the candidate pool fed into transit corroboration now prefers EVERY
#     plausible-age window over a hard-implausible-age one regardless of
#     raw dasha score (see _select_candidate_pool and
#     app.astro.life_stage_plausibility.is_hard_implausible_age), instead
#     of a plain top-8-by-raw-score truncation that could throw away every
#     plausible-age window before age was ever considered.
#   - a window that's still hard-implausible-age even after that (no
#     plausible-age alternative existed anywhere in the search horizon) is
#     now surfaced as a REINTERPRETED signal rather than a literal one (see
#     the new `literal_event_plausible` field and
#     prediction_templates.py's reinterpretation sentence) — "family
#     finances" instead of personal wealth, "family responsibility" instead
#     of a literal childbirth, etc. — instead of silently presenting an
#     adolescent's chart as a wealth-earning adult's.
# v12: candidate windows now also need real Antardasha-level evidence — the
# window's OWN Antardasha lord must be the category's house lord or a
# karaka — to outrank one without it, regardless of raw dasha score. Found
# by comparing this engine's own output against independent chart reads: a
# "strongest past wealth period" answer whose Antardasha lord was neither
# the wealth house lord nor a wealth karaka, and whose entire score of 0.28
# came from a Mahadasha-level karaka match alone (a much weaker, backdrop-
# only signal — see app.services.prediction_service._evidence_level),
# was still winning purely because nothing else was left standing after
# candidate-pool truncation. Evidence now outranks age-plausibility in both
# _select_candidate_pool and _rerank_with_transit_bonus's priority order
# (see _pool_priority) — a well-evidenced window at an implausible age is a
# more meaningful signal about the event (just needing reinterpretation —
# see v11) than a plausible-age window that isn't really about the event at
# all. Surfaced via a new evidence field and an honest reason-text note for
# a backdrop-only window, instead of it reading the same as a
# directly-evidenced one.
# v13: that evidence field is now a 3-level `evidence_level` ("house_lord_
# antardasha" > "karaka_antardasha" > "backdrop_only") instead of a plain
# direct/not-direct boolean — found by comparing this engine's own output
# against independent chart reads: a "strongest past marriage period"
# answer whose Antardasha lord was Venus (a real but generic karaka shared
# with wealth — see app.astro.event_karakas) read identically ("direct
# evidence") to one where the actual 7th lord was running, losing the real
# classical distinction between "this IS the house of the event" and "this
# planet ALSO happens to signify the event among others." House-lord-level
# evidence now outranks karaka-level in both _select_candidate_pool and
# _rerank_with_transit_bonus's priority order (see _EVIDENCE_RANK), same
# convention as v12's evidence-before-backdrop change.
# v14: fixes a real selection bug v13 introduced — evidence level was
# outranking age-plausibility in _pool_priority, so a hard-implausible-age
# window with strong evidence (the actual house lord's own Antardasha)
# could beat a plausible-age window with merely real (karaka-level)
# evidence, even when that plausible one was sitting right there in the
# same candidate pool. Found by comparing this engine's own output against
# independent chart reads: one chart's "strongest past marriage period"
# was the 7th lord's own Antardasha at age ~2.6 — reinterpreted as
# non-literal — while a Venus Antardasha at age ~17 (plausible, real
# evidence) went unchosen in the same pool. Age-plausibility now decides
# first; evidence level only breaks ties within the same age-plausibility
# bucket (see _pool_priority's docstring).
_TIMING_ALGO_VERSION = 14

# The 7 classical planets Shadbala scores (Rahu/Ketu excluded — see
# app.astro.shadbala's module docstring). MINIMUM_RUPAS.keys() is the public
# source of truth for exactly which planets that is.
_SHADBALA_PLANETS = tuple(MINIMUM_RUPAS)

# Bump only when _significator_strength's own logic changes (dignity/
# dusthana/combustion, aspects/conjunctions, Vargottama, or Shadbala) — NOT
# on every _TIMING_ALGO_VERSION bump, since most of those (dasha-relationship
# weighting, transit corroboration/obstruction, age plausibility, karaka
# specificity) change how the strength dict gets USED, not the dict itself.
# Keeping this separate means a v10-style scoring fix doesn't needlessly
# invalidate (and force a full Shadbala rebuild for) this cache too.
_SIGNIFICATOR_STRENGTH_ALGO_VERSION = 1


def _shadbala_chart_inputs(birth: BirthDataOut) -> ShadbalaChartInputs:
    """Builds app.astro.shadbala's per-chart input from raw ephemeris data —
    computed fresh from `birth` rather than read off the cached D1
    ChartResponse, since Shadbala needs each planet's real SPEED (for
    Cheshta Bala) and the natal Lagna's exact longitude (for Dig Bala),
    neither of which the D1 chart cache exposes. Blocking (calls
    app.astro.ephemeris's swisseph wrappers directly, including sunrise/
    sunset root-finding) — callers MUST run this via anyio.to_thread.run_sync,
    same rule as every other ephemeris-touching call in this app."""
    birth_dt = birth_datetime_utc(birth)
    jd_ut = julian_day_ut(birth_dt)
    positions = all_planet_positions(jd_ut)
    lagna_longitude = ascendant_sidereal(jd_ut, birth.latitude, birth.longitude)
    lagna_sign = sign_index(lagna_longitude)

    natal_sign = {p: sign_index(positions[p].longitude) for p in _SHADBALA_PLANETS}
    natal_house = {p: house_number(natal_sign[p], lagna_sign) for p in _SHADBALA_PLANETS}
    natal_longitude = {p: positions[p].longitude for p in _SHADBALA_PLANETS}
    # Computed ONCE per chart, not per planet — see ShadbalaChartInputs's
    # docstring for the redundant-7x-recomputation bug this avoids.
    birth_window, weekday_lord, current_hora_lord = compute_time_of_day_facts(jd_ut, birth.latitude, birth.longitude)

    return ShadbalaChartInputs(
        natal_planet_sign=natal_sign,
        natal_planet_longitude=natal_longitude,
        natal_planet_speed={p: positions[p].speed for p in _SHADBALA_PLANETS},
        natal_planet_house=natal_house,
        natal_planet_d9_sign={p: navamsa_sign_index(positions[p].longitude) for p in _SHADBALA_PLANETS},
        natal_planet_varga_signs={
            p: {
                "D2": hora_sign_index(positions[p].longitude),
                "D3": drekkana_sign_index(positions[p].longitude),
                "D7": saptamsa_sign_index(positions[p].longitude),
                "D12": dwadashamsa_sign_index(positions[p].longitude),
                "D30": trimshamsa_sign_index(positions[p].longitude),
            }
            for p in _SHADBALA_PLANETS
        },
        natal_planet_declination={p: declination(jd_ut, p) for p in _SHADBALA_PLANETS},
        natal_planet_aspect_multiplier={
            p: aspect_and_conjunction_multiplier(p, natal_house[p], natal_house) for p in _SHADBALA_PLANETS
        },
        lagna_longitude=lagna_longitude,
        birth_jd_ut=jd_ut,
        latitude=birth.latitude,
        longitude=birth.longitude,
        birth_window=birth_window,
        weekday_lord=weekday_lord,
        current_hora_lord=current_hora_lord,
    )


def _significator_strength(d1, birth: BirthDataOut) -> dict[str, float]:
    """Natal-strength multiplier per planet in this D1 chart, for scaling the
    window scanner's classical dasha-rule weights (see marriage_rules/
    event_rules `strength` parameter) by how strong each significator
    actually is here — not just which planet's dasha it is. BLOCKING (builds
    and runs full Shadbala) — callers MUST run this via
    anyio.to_thread.run_sync."""
    planet_sign = {p.planet: p.sign_index for p in d1.planets}
    planet_house = {p.planet: p.house for p in d1.planets}
    planet_longitude = {p.planet: p.sign_index * 30 + (p.degree_in_sign or 0.0) for p in d1.planets}
    shadbala_chart = _shadbala_chart_inputs(birth)
    shadbala_results = compute_all_shadbala(shadbala_chart)
    return significator_strength_multipliers(
        planet_sign, planet_house, planet_longitude,
        planet_d9_sign_index=shadbala_chart.natal_planet_d9_sign,
        shadbala_results=shadbala_results,
    )


def _significator_strength_select_stmt(profile: BirthProfile):
    return select(SignificatorStrengthCache).where(
        SignificatorStrengthCache.user_id == profile.user_id,
        SignificatorStrengthCache.birth_profile_version == profile.version,
    )


async def _get_cached_significator_strength(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, d1
) -> dict[str, float]:
    """Cached wrapper around _significator_strength — identical output for a
    given birth profile regardless of which of the 5 timing endpoints
    (marriage, or life-event career/wealth/children/foreign_travel) or which
    direction (future/past) asked for it, so it's computed once per
    (user, birth_profile_version) and reused across all of them instead of
    rebuilding the full Shadbala chart on every single call."""
    select_stmt = _significator_strength_select_stmt(profile)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if cached_row is not None and cached_row.data.get("algo_version") == _SIGNIFICATOR_STRENGTH_ALGO_VERSION:
        return cached_row.data["strength"]

    strength = await anyio.to_thread.run_sync(_significator_strength, d1, birth)
    data = {"strength": strength, "algo_version": _SIGNIFICATOR_STRENGTH_ALGO_VERSION}

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        return strength

    row = SignificatorStrengthCache(
        user_id=profile.user_id, birth_profile_version=profile.version, data=data
    )
    data, _was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)
    return data["strength"]


def _natal_planet_sign_index(d1) -> dict[str, int]:
    """Natal sign index per planet, the per-chart input
    app.astro.transit_corroboration needs to compute a corroborating
    transit's Ashtakavarga (the 7 classical planets' natal positions plus
    the natal Lagna, already available separately as d1.lagna_sign_index,
    are the 8 Bhinnashtakavarga contributors)."""
    return {p.planet: p.sign_index for p in d1.planets}


# Turns the continuous strength multiplier back into plain language for
# marriage_window_reason_text/life_event_reason_text's `natal_strength`
# parameter. Deliberately silent (None) for the middle ground — most
# significators are neither clearly strong nor clearly weak, and a note on
# every single window would read as noise, not signal. 1.25 is the exact
# multiplier for a clean own-sign placement; 0.8 sits just above a single
# affliction alone (dusthana-only or combust-only) so ONE mild affliction
# doesn't get called "weak", but any stronger combination does.
def _natal_strength_category(multiplier: float) -> Literal["strong", "weak"] | None:
    if multiplier >= 1.25:
        return "strong"
    if multiplier <= 0.8:
        return "weak"
    return None


def _significator_retrograde(d1) -> dict[str, bool]:
    """Per-planet retrograde (Vakri) status from this D1 chart — already
    computed for every chart (see app.astro.charts.ChartResult) but never
    surfaced anywhere in the Prediction Engine until now. Deliberately NOT
    folded into the strength/score multiplier above: classical sources
    disagree on whether retrograde strengthens a planet (Shadbala's Cheshta
    Bala treats it as a strength gain) or weakens/delays its results (the
    much more common everyday reading), so this app takes no side — it only
    surfaces the fact and lets the reader weigh it, same honesty rule as
    every other documented simplification in app.astro."""
    return {p.planet: p.retrograde for p in d1.planets}


def _window_age_years(window: ScoredWindow, birth_dt: datetime) -> float:
    return (window.start - birth_dt).days / DAYS_PER_YEAR


def _is_hard_implausible(window: ScoredWindow, birth_dt: datetime, event_category: EventCategory) -> bool:
    return is_hard_implausible_age(event_category, _window_age_years(window, birth_dt))


EvidenceLevel = Literal["house_lord_antardasha", "karaka_antardasha", "backdrop_only"]

# Lower ranks first — see _pool_priority. A window's own Antardasha being
# the category's house lord (always category-specific by construction,
# classically the strongest signal — see marriage_rules/event_rules) is a
# STRONGER claim than its own Antardasha merely being a karaka (real
# classical evidence, but a generic significator that may also serve other
# categories — see app.astro.event_karakas), which in turn is stronger than
# only qualifying through the broader Mahadasha (see _evidence_level).
_EVIDENCE_RANK: dict[EvidenceLevel, int] = {
    "house_lord_antardasha": 0, "karaka_antardasha": 1, "backdrop_only": 2,
}


def _evidence_level(window: ScoredWindow) -> EvidenceLevel:
    """Classifies how directly THIS SPECIFIC window's own Antardasha (not
    just the broader Mahadasha it happens to fall inside) ties to the
    event — see marriage_rules/event_rules' reason keys, all of which mark
    an Antardasha-level match with "_antardasha" somewhere in the key
    (either exactly, e.g. "seventh_lord_antardasha", or with the karaka
    appended, e.g. "wealth_karaka_antardasha_Ju" — hence a substring check,
    not endswith), and mark a house-lord (as opposed to karaka) match with
    "house_lord" (life-event's generic naming) or "seventh_lord"
    (marriage's own naming for the same concept).

    Originally just `_has_direct_evidence` — a plain bool lumping the house
    lord's own Antardasha together with a mere karaka's own Antardasha as
    equally "direct". Found by comparing this engine's own output against
    independent chart reads: a "strongest past marriage period" answer
    whose Antardasha lord was Venus (a real but generic karaka) rather than
    the actual 7th lord read the same ("direct evidence") as a window where
    the 7th lord itself was running — losing a real, classically meaningful
    distinction between "this IS the house of the event" and "this planet
    ALSO happens to signify the event among others". A window whose only
    reason keys are Mahadasha-level ("*_mahadasha") and/or a dasha-
    relationship note is still "backdrop_only": it scores above zero, but
    nothing about this particular narrower window ties it to the event at
    all — see the original real-world case this caught: a "strongest past
    wealth period" answer whose Antardasha lord was neither the wealth
    house lord nor a wealth karaka, winning purely because its Mahadasha
    lord happened to be a (specificity-discounted) karaka, with a resulting
    score of 0.28."""
    antardasha_keys = [key for key in window.reason_keys if "_antardasha" in key]
    if any("house_lord" in key or "seventh_lord" in key for key in antardasha_keys):
        return "house_lord_antardasha"
    if antardasha_keys:
        return "karaka_antardasha"
    return "backdrop_only"


def _effective_score(
    window: ScoredWindow, check: TransitCheck, birth_dt: datetime, event_category: EventCategory
) -> float:
    score = window.score
    if check.corroborated:
        score += _TRANSIT_CORROBORATION_BONUS * check.corroboration_strength
    if check.obstructed:
        score -= _TRANSIT_OBSTRUCTION_PENALTY * check.obstruction_fraction
    age_years = _window_age_years(window, birth_dt)
    # A real-world sanity layer, not a classical one — see
    # app.astro.life_stage_plausibility for why this exists: without it, a
    # chart's own infancy (or its 60s+) can mathematically outrank a window
    # at a plausible age purely on dasha-relationship scoring, with nothing
    # to say "a newborn can't have a career."
    return score * age_plausibility_multiplier(event_category, age_years)


def _pool_priority(
    window: ScoredWindow, birth_dt: datetime, event_category: EventCategory
) -> tuple[bool, int]:
    """Lower sorts first — see _select_candidate_pool and
    _rerank_with_transit_bonus, which both use this as their primary sort
    key ahead of score. Age-plausibility outranks evidence level: a window
    at a hard-implausible age should NOT beat a plausible-age window just
    because the implausible one happens to be the actual house lord's own
    Antardasha rather than "only" a karaka's.

    This inverts an earlier version of this function (evidence-before-age)
    that turned out to be wrong in practice — found by comparing this
    engine's own output against independent chart reads: for one chart, the
    engine's "strongest past marriage period" was the 7th lord's own
    Antardasha at age ~2.6 (house_lord_antardasha, hence highest evidence
    rank), reinterpreted as non-literal — while a Venus Antardasha at age
    ~17 (karaka_antardasha, plausible-age, real if secondary evidence) sat
    right there in the same candidate pool, unchosen, purely because
    evidence outranked age at the time. Presenting an unexplainable age-3
    "marriage" signal (needing reinterpretation) is a worse answer than a
    mildly-early but still literal, easily-explained age-17 one — so
    age-plausibility now decides first, and evidence level (see
    _EVIDENCE_RANK — house-lord-level still outranks karaka-level) only
    breaks ties WITHIN the same age-plausibility bucket."""
    return (_is_hard_implausible(window, birth_dt, event_category), _EVIDENCE_RANK[_evidence_level(window)])


def _select_candidate_pool(
    windows: list[ScoredWindow], birth_dt: datetime, event_category: EventCategory
) -> list[ScoredWindow]:
    """Picks the _CANDIDATE_POOL_SIZE windows to run the (comparatively
    expensive) transit-corroboration check on, preferring every window with
    stronger Antardasha-level evidence for this event (see _evidence_level)
    and every plausible-age window (see app.astro.life_stage_plausibility.
    is_hard_implausible_age) over ones without, regardless of raw dasha
    score (see _pool_priority for the exact tie-break order).

    Without this, a plain top-N-by-raw-score truncation of `windows` (which
    `find_marriage_windows`/`find_event_windows` already sorts by dasha
    score alone) can throw away every well-evidenced or plausible-age
    window before either transit corroboration or these checks ever get a
    chance to consider them — found by comparing this engine's own output
    against independent chart reads: a chart's own adolescence structurally
    tends to score very highly (see that module's docstring), so for a
    person whose full lifetime dasha timeline is being searched (a
    past-direction query for an older adult), the naive top-8-by-raw-score
    pool could be entirely adolescent/childhood windows, or entirely
    Mahadasha-only-evidence windows, with nothing better left to even
    compare against.

    `windows` is assumed already sorted by raw score — Python's sort is
    stable, so windows keep their relative raw-score order within each
    `_pool_priority` bucket; this re-orders buckets, it doesn't re-rank
    within one."""
    ordered = sorted(windows, key=lambda w: _pool_priority(w, birth_dt, event_category))
    return ordered[:_CANDIDATE_POOL_SIZE]


def _rerank_with_transit_bonus(
    scored_pairs: list[tuple[ScoredWindow, TransitCheck]], birth_dt: datetime, event_category: EventCategory
) -> list[tuple[ScoredWindow, TransitCheck]]:
    """Re-sorts a (window, transit_check) pool by dasha score PLUS the
    Ashtakavarga-scaled corroboration bonus MINUS the obstruction-fraction
    penalty, scaled by real-world age plausibility (see _effective_score),
    then trims to the final count — same tie-break (earliest start) as the
    underlying dasha-only sort.

    A window at a hard-implausible age (see _is_hard_implausible) always
    sorts AFTER every plausible-age window, regardless of effective score
    or evidence level — same priority order as _select_candidate_pool's
    _pool_priority (age before evidence). A technically well-supported
    window (the correct house lord's own Antardasha) at, say, age 3 for
    "marriage" should never outrank a plausible-age window just because its
    score survived being multiplied down or because it has stronger
    evidence — presenting an unexplainable, reinterpreted result is worse
    than a mildly-early but still literal one (see _pool_priority's
    docstring for the real case that established this ordering). Within
    the same age-plausibility bucket, weaker evidence (see _evidence_level)
    still sorts after stronger — a window whose only tie to the event is
    its broader Mahadasha shouldn't outrank one whose own Antardasha is
    genuinely the house lord or a karaka, all else equal. Either an
    implausible-age or a backdrop-only window can still appear in the
    final result (flagged, not silently presented as strong — see
    `evidence_level`/`literal_event_plausible` and
    prediction_templates.py) when _select_candidate_pool couldn't find
    enough better candidates to fill the pool."""
    scored_pairs.sort(
        key=lambda pair: (
            *_pool_priority(pair[0], birth_dt, event_category),
            -_effective_score(pair[0], pair[1], birth_dt, event_category),
            pair[0].start,
        )
    )
    return scored_pairs[:_FINAL_WINDOW_COUNT]


def _search_bounds(
    direction: Direction, birth_dt: datetime, now: datetime, mahadashas: list[Mahadasha] | None = None
) -> tuple[datetime, float]:
    """Where to point the window scanner — the entire past (birth to now),
    or a forward-looking horizon out to +20 years from now. Same scanner
    (app.astro.event_window_scanner.scan_dasha_windows) either way; this is
    purely a different choice of bounds, not new astro logic.

    For "future", if `mahadashas` is given and an Antardasha is ALREADY
    running right now, the search starts from THAT Antardasha's real start
    (in the past) rather than from `now` — otherwise a currently-active,
    genuinely strong window gets silently clipped to only its remaining
    tail (a fragment of its true score) in the future direction, while its
    already-elapsed portion only shows up as a separate, also-fragmentary
    result in the PAST direction. Neither fragment alone reflects "you are
    in a real, strong window right now" as the one continuous fact it is;
    starting the future search from the Antardasha's true start reports it
    whole, with its true dates and true score, in the direction most users
    check by default. The horizon is extended by the same amount pulled
    backward, so the search still reaches +20 years from `now`, not from
    this earlier start."""
    if direction == "past":
        age_years = (now - birth_dt).days / DAYS_PER_YEAR
        return birth_dt, max(age_years, 0.0)

    from_dt = now
    if mahadashas is not None:
        current_maha = find_current_mahadasha(mahadashas, now)
        current_antar = find_current_antardasha(current_maha, now) if current_maha is not None else None
        if current_antar is not None:
            from_dt = current_antar.start
    horizon_years = _FUTURE_HORIZON_YEARS + (now - from_dt).days / DAYS_PER_YEAR
    return from_dt, horizon_years

MAX_MULTI_YEARS = 3


def _year_select_stmt(profile: BirthProfile, year: int, language: Language):
    return select(YearOutlookCache).where(
        YearOutlookCache.user_id == profile.user_id,
        YearOutlookCache.year == year,
        YearOutlookCache.language == language,
        YearOutlookCache.birth_profile_version == profile.version,
    )


async def get_year_ahead(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, year: int, language: Language
) -> YearOutlookResponse:
    _REQUIRED_CACHE_KEYS = ("quarters", "varsheshwar")
    select_stmt = _year_select_stmt(profile, year, language)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if cached_row is not None and all(k in cached_row.data for k in _REQUIRED_CACHE_KEYS):
        return YearOutlookResponse(year=year, language=language, cached=True, **cached_row.data)

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    sun = next(p for p in d1.planets if p.planet == "Su")
    planet_house = {p.planet: p.house for p in d1.planets}
    planet_sign = {p.planet: p.sign_index for p in d1.planets}

    birth_dt = birth_datetime_utc(birth)
    sun_longitude = sun.sign_index * 30 + (sun.degree_in_sign or 0.0)

    def _compute_varshaphala_and_bounds():
        varshaphala = compute_varshaphala(
            birth_dt, sun_longitude, d1.lagna_sign_index, birth.latitude, birth.longitude, year
        )
        year_end = compute_solar_return(birth_dt, sun_longitude, year + 1)
        return varshaphala, year_end

    varshaphala, year_end = await anyio.to_thread.run_sync(_compute_varshaphala_and_bounds)
    year_start = varshaphala.solar_return_dt
    quarter_span = (year_end - year_start) / 4

    mahadashas = await get_mahadashas_raw(db, profile, birth)

    quarter_bounds = []
    cursor = year_start
    for i in range(4):
        q_end = cursor + quarter_span if i < 3 else year_end
        quarter_bounds.append((cursor, q_end))
        cursor = q_end
    midpoints = [q_start + (q_end - q_start) / 2 for q_start, q_end in quarter_bounds]

    def _quarter_transit_snapshots():
        return [compute_transit_snapshot(at, d1.lagna_sign_index, moon.sign_index) for at in midpoints]

    snapshots = await anyio.to_thread.run_sync(_quarter_transit_snapshots)

    varsheshwar_dignity = planet_dignity(varshaphala.varsheshwar, planet_sign[varshaphala.varsheshwar])
    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN

    quarters_out = []
    quarter_ratings = []
    for (q_start, q_end), midpoint, snapshot in zip(quarter_bounds, midpoints, snapshots):
        maha = find_current_mahadasha(mahadashas, midpoint)
        antar = find_current_antardasha(maha, midpoint) if maha is not None else None
        if maha is None or antar is None:
            # The dasha timeline (one full ~120-year Vimshottari cycle from
            # birth) should cover any realistic requested year — skip
            # gracefully rather than crash if a caller ever requests a year
            # past that horizon.
            continue

        antar_house = planet_house.get(antar.lord)
        antar_dignity = planet_dignity(antar.lord, planet_sign[antar.lord]) if antar.lord in planet_sign else "neutral"
        if antar_house is None:
            continue

        sade_sati = compute_sade_sati(moon.sign_index, snapshot.planet_sign_index["Sa"])
        dosha_notes = []
        if sade_sati.is_active:
            dosha_notes.append(
                f"शनि की साढ़े साती इस दौरान {sade_sati.phase} चरण में है।"
                if language == "hi" else
                f"Saturn's Sade Sati is in its {sade_sati.phase} phase during this stretch."
            )

        text = year_outlook_text(
            antardasha_lord=antar.lord,
            antardasha_lord_house=antar_house,
            antardasha_lord_dignity=antar_dignity,
            varsheshwar=varshaphala.varsheshwar,
            varsheshwar_dignity=varsheshwar_dignity,
            muntha_house=varshaphala.muntha_house_from_varsha_lagna,
            jupiter_transit_house_from_moon=snapshot.planet_house_from_moon["Ju"],
            saturn_transit_house_from_moon=snapshot.planet_house_from_moon["Sa"],
            active_dosha_notes=dosha_notes,
            language=language,
        )
        quarters_out.append(
            {
                # ISO strings, not date objects — the JSON cache column's
                # default encoder can't serialize a bare `date` (see
                # windows_out below in get_marriage_timing for the same
                # convention). Pydantic parses an ISO date string back into
                # a `date` field just as readily as a real `date` object, so
                # this is transparent to both the cache write and the
                # immediate (uncached) response construction below.
                "start_date": q_start.date().isoformat(),
                "end_date": q_end.date().isoformat(),
                "dominant_dasha_lord": antar.lord,
                "dominant_dasha_lord_name": names[antar.lord],
                "theme": text["theme"],
                "rating": text["rating"],
                "opportunities": text["opportunities"],
                "risks": text["risks"],
            }
        )
        quarter_ratings.append(text["rating"])

    overall_rating = round(sum(quarter_ratings) / len(quarter_ratings)) if quarter_ratings else 5
    overall_theme = overall_year_theme(
        varshaphala.varsheshwar, varsheshwar_dignity, varshaphala.muntha_house_from_varsha_lagna, language
    )

    data = {
        "overall_rating": overall_rating,
        "overall_theme": overall_theme,
        "varsheshwar": varshaphala.varsheshwar,
        "varsheshwar_name": names[varshaphala.varsheshwar],
        "muntha_house": varshaphala.muntha_house_from_varsha_lagna,
        "quarters": quarters_out,
    }

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        return YearOutlookResponse(year=year, language=language, cached=False, **data)

    row = YearOutlookCache(
        user_id=profile.user_id, year=year, language=language, birth_profile_version=profile.version, data=data
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)
    return YearOutlookResponse(year=year, language=language, cached=was_race, **data)


async def get_multi_year_outlook(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, years: int, language: Language
) -> MultiYearOutlookResponse:
    years = min(years, MAX_MULTI_YEARS)
    current_year = datetime.now(timezone.utc).year
    results = [await get_year_ahead(db, profile, birth, current_year + i, language) for i in range(years)]
    return MultiYearOutlookResponse(years=results)


def _marriage_select_stmt(profile: BirthProfile, direction: Direction, language: Language):
    return select(MarriageTimingCache).where(
        MarriageTimingCache.user_id == profile.user_id,
        MarriageTimingCache.direction == direction,
        MarriageTimingCache.language == language,
        MarriageTimingCache.birth_profile_version == profile.version,
    )


async def get_marriage_timing(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, language: Language, direction: Direction = "future"
) -> MarriageTimingResponse:
    _REQUIRED_CACHE_KEYS = ("windows",)
    select_stmt = _marriage_select_stmt(profile, direction, language)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if (
        cached_row is not None
        and all(k in cached_row.data for k in _REQUIRED_CACHE_KEYS)
        and cached_row.data.get("algo_version") == _TIMING_ALGO_VERSION
    ):
        return MarriageTimingResponse(language=language, direction=direction, cached=True, **cached_row.data)

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    mars = next(p for p in d1.planets if p.planet == "Ma")
    mahadashas = await get_mahadashas_raw(db, profile, birth)
    seventh_lord = house_lord(7, d1.lagna_sign_index)
    birth_dt = birth_datetime_utc(birth)
    now = datetime.now(timezone.utc)
    from_dt, horizon_years = _search_bounds(direction, birth_dt, now, mahadashas)
    strength = await _get_cached_significator_strength(db, profile, birth, d1)
    retrograde = _significator_retrograde(d1)
    natal_planet_sign = _natal_planet_sign_index(d1)

    def _compute_windows():
        raw_windows = find_marriage_windows(
            mahadashas, seventh_lord, from_dt, horizon_years, top_n=_RAW_SCAN_POOL_SIZE, strength=strength
        )
        windows = _select_candidate_pool(raw_windows, birth_dt, "marriage")
        pairs = [
            (w, corroborate_with_transits(w, d1.lagna_sign_index, moon.sign_index, natal_planet_sign))
            for w in windows
        ]
        return _rerank_with_transit_bonus(pairs, birth_dt, "marriage")

    scored_windows = await anyio.to_thread.run_sync(_compute_windows)

    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
    seventh_lord_name = names[seventh_lord]
    windows_out = []
    for w, check in scored_windows:
        age_years = (w.start - birth_dt).days / DAYS_PER_YEAR
        age_multiplier = age_plausibility_multiplier("marriage", age_years)
        literal_event_plausible = not is_hard_implausible_age("marriage", age_years)
        evidence_level = _evidence_level(w)
        reason = marriage_window_reason_text(
            w.reason_keys, seventh_lord_name, w.antardasha_lord, check.corroborated, language, tense=direction,
            natal_strength=_natal_strength_category(strength.get(w.antardasha_lord, 1.0)),
            antardasha_lord_retrograde=retrograde.get(w.antardasha_lord, False),
            transit_obstructing_planet=names[check.obstructing_planet] if check.obstructing_planet else None,
            age_implausibility=is_implausible_age("marriage", age_years),
            literal_event_plausible=literal_event_plausible,
            evidence_level=evidence_level,
        )
        windows_out.append(
            {
                # ISO strings, not date objects — see the matching comment
                # in get_year_ahead above.
                "start_date": w.start.date().isoformat(),
                "end_date": w.end.date().isoformat(),
                "mahadasha_lord": w.mahadasha_lord,
                "mahadasha_lord_name": names[w.mahadasha_lord],
                "antardasha_lord": w.antardasha_lord,
                "antardasha_lord_name": names[w.antardasha_lord],
                "score": w.score,
                "reason": reason,
                "transit_corroborated": check.corroborated,
                "transit_corroboration_strength": check.corroboration_strength,
                "transit_obstructed": check.obstructed,
                "transit_obstruction_fraction": check.obstruction_fraction,
                "age_plausibility_multiplier": age_multiplier,
                "literal_event_plausible": literal_event_plausible,
                "evidence_level": evidence_level,
            }
        )

    manglik = compute_manglik_facts(
        mars_sign_index=mars.sign_index, mars_house_from_lagna=mars.house, moon_sign_index=moon.sign_index
    )
    manglik_note = None
    if manglik.is_manglik:
        manglik_note = (
            "आपकी कुंडली में मंगलिक दोष है — कई परिवार विवाह से पहले साथी की कुंडली से इसका मिलान करते हैं।"
            if language == "hi" else
            "Your chart shows Manglik (Mangal) Dosha — many families match this specifically against a "
            "partner's chart before marriage."
        )

    data = {"windows": windows_out, "manglik_note": manglik_note, "algo_version": _TIMING_ALGO_VERSION}

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        return MarriageTimingResponse(language=language, direction=direction, cached=False, **data)

    row = MarriageTimingCache(
        user_id=profile.user_id, direction=direction, language=language, birth_profile_version=profile.version,
        data=data,
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)
    return MarriageTimingResponse(language=language, direction=direction, cached=was_race, **data)


def _life_event_select_stmt(profile: BirthProfile, event_type: EventType, direction: Direction, language: Language):
    return select(LifeEventTimingCache).where(
        LifeEventTimingCache.user_id == profile.user_id,
        LifeEventTimingCache.event_type == event_type,
        LifeEventTimingCache.direction == direction,
        LifeEventTimingCache.language == language,
        LifeEventTimingCache.birth_profile_version == profile.version,
    )


async def get_life_event_timing(
    db: AsyncSession,
    profile: BirthProfile,
    birth: BirthDataOut,
    event_type: EventType,
    language: Language,
    direction: Direction = "future",
) -> LifeEventTimingResponse:
    """Career/wealth/children/foreign-travel timing — the generic sibling of
    get_marriage_timing above, built on the same window scanner via
    app.astro.life_event_timing instead of app.astro.marriage_timing."""
    _REQUIRED_CACHE_KEYS = ("windows",)
    select_stmt = _life_event_select_stmt(profile, event_type, direction, language)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if (
        cached_row is not None
        and all(k in cached_row.data for k in _REQUIRED_CACHE_KEYS)
        and cached_row.data.get("algo_version") == _TIMING_ALGO_VERSION
    ):
        return LifeEventTimingResponse(
            event_type=event_type, language=language, direction=direction, cached=True, **cached_row.data
        )

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    mahadashas = await get_mahadashas_raw(db, profile, birth)
    house_lord_planet = house_lord(LIFE_EVENT_HOUSE[event_type], d1.lagna_sign_index)
    birth_dt = birth_datetime_utc(birth)
    now = datetime.now(timezone.utc)
    from_dt, horizon_years = _search_bounds(direction, birth_dt, now, mahadashas)
    strength = await _get_cached_significator_strength(db, profile, birth, d1)
    retrograde = _significator_retrograde(d1)
    natal_planet_sign = _natal_planet_sign_index(d1)

    def _compute_windows() -> list[tuple[ScoredWindow, TransitCheck]]:
        raw_windows = find_event_windows(
            mahadashas, event_type, house_lord_planet, from_dt, horizon_years,
            top_n=_RAW_SCAN_POOL_SIZE, strength=strength,
        )
        windows = _select_candidate_pool(raw_windows, birth_dt, event_type)
        pairs = [
            (
                w,
                corroborate_life_event_with_transits(
                    event_type, w, d1.lagna_sign_index, moon.sign_index, natal_planet_sign
                ),
            )
            for w in windows
        ]
        return _rerank_with_transit_bonus(pairs, birth_dt, event_type)

    scored_windows = await anyio.to_thread.run_sync(_compute_windows)

    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
    house_lord_name = names[house_lord_planet]
    windows_out = []
    for w, check in scored_windows:
        age_years = (w.start - birth_dt).days / DAYS_PER_YEAR
        age_multiplier = age_plausibility_multiplier(event_type, age_years)
        literal_event_plausible = not is_hard_implausible_age(event_type, age_years)
        evidence_level = _evidence_level(w)
        reason = life_event_reason_text(
            event_type, w.reason_keys, house_lord_name, w.antardasha_lord, check.corroborated, language,
            tense=direction,
            natal_strength=_natal_strength_category(strength.get(w.antardasha_lord, 1.0)),
            antardasha_lord_retrograde=retrograde.get(w.antardasha_lord, False),
            transit_obstructing_planet=names[check.obstructing_planet] if check.obstructing_planet else None,
            age_implausibility=is_implausible_age(event_type, age_years),
            literal_event_plausible=literal_event_plausible,
            evidence_level=evidence_level,
        )
        windows_out.append(
            {
                "start_date": w.start.date().isoformat(),
                "end_date": w.end.date().isoformat(),
                "mahadasha_lord": w.mahadasha_lord,
                "mahadasha_lord_name": names[w.mahadasha_lord],
                "antardasha_lord": w.antardasha_lord,
                "antardasha_lord_name": names[w.antardasha_lord],
                "score": w.score,
                "reason": reason,
                "transit_corroborated": check.corroborated,
                "transit_corroboration_strength": check.corroboration_strength,
                "transit_obstructed": check.obstructed,
                "transit_obstruction_fraction": check.obstruction_fraction,
                "age_plausibility_multiplier": age_multiplier,
                "literal_event_plausible": literal_event_plausible,
                "evidence_level": evidence_level,
            }
        )

    data = {"windows": windows_out, "algo_version": _TIMING_ALGO_VERSION}

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        return LifeEventTimingResponse(
            event_type=event_type, language=language, direction=direction, cached=False, **data
        )

    row = LifeEventTimingCache(
        user_id=profile.user_id,
        event_type=event_type,
        direction=direction,
        language=language,
        birth_profile_version=profile.version,
        data=data,
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)
    return LifeEventTimingResponse(
        event_type=event_type, language=language, direction=direction, cached=was_race, **data
    )


def _life_theme_select_stmt(profile: BirthProfile, target_date: date, language: Language):
    return select(LifeThemeCache).where(
        LifeThemeCache.user_id == profile.user_id,
        LifeThemeCache.target_date == target_date,
        LifeThemeCache.language == language,
        LifeThemeCache.birth_profile_version == profile.version,
    )


async def get_life_theme(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, target_date: date, language: Language
) -> LifeThemeResponse:
    """The general "what was going on then" reflection for ANY date (almost
    always past, but nothing stops asking about today or a future date too)
    — not tied to one life-event type. Reuses find_current_mahadasha/
    antardasha and compute_transit_snapshot exactly as every other feature
    in this app does, just pointed at an arbitrary target date instead of
    "now"; the only genuinely new computation is Sade Sati/Dhaiya at that
    date, both already-existing dosha checks (compute_sade_sati,
    compute_dhaiya) given a transit snapshot for any date."""
    _REQUIRED_CACHE_KEYS = ("mahadasha_lord", "theme")
    select_stmt = _life_theme_select_stmt(profile, target_date, language)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if cached_row is not None and all(k in cached_row.data for k in _REQUIRED_CACHE_KEYS):
        return LifeThemeResponse(target_date=target_date, language=language, cached=True, **cached_row.data)

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    mahadashas = await get_mahadashas_raw(db, profile, birth)
    at = datetime(target_date.year, target_date.month, target_date.day, 12, 0, tzinfo=timezone.utc)

    def _compute():
        maha = find_current_mahadasha(mahadashas, at)
        antar = find_current_antardasha(maha, at) if maha is not None else None
        snapshot = compute_transit_snapshot(at, d1.lagna_sign_index, moon.sign_index)
        return maha, antar, snapshot

    mahadasha_at, antardasha_at, snapshot = await anyio.to_thread.run_sync(_compute)

    if mahadasha_at is None or antardasha_at is None:
        # Outside the single ~120-year Vimshottari cycle this app computes
        # from birth — realistically only reachable for a target_date far
        # beyond a human lifespan. Nothing real to report.
        raise ValueError("target_date is outside the computable Dasha timeline for this chart")

    sade_sati = compute_sade_sati(moon.sign_index, snapshot.planet_sign_index["Sa"])
    dhaiya = compute_dhaiya(moon.sign_index, snapshot.planet_sign_index["Sa"])

    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
    generated = life_theme_text(
        mahadasha_lord=mahadasha_at.lord,
        antardasha_lord=antardasha_at.lord,
        sade_sati_active=sade_sati.is_active,
        dhaiya_active=dhaiya.is_active,
        language=language,
    )

    data = {
        "mahadasha_lord": mahadasha_at.lord,
        "mahadasha_lord_name": names[mahadasha_at.lord],
        "antardasha_lord": antardasha_at.lord,
        "antardasha_lord_name": names[antardasha_at.lord],
        "sade_sati_active": sade_sati.is_active,
        "dhaiya_active": dhaiya.is_active,
        "rating": generated["rating"],
        "theme": generated["theme"],
    }

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        return LifeThemeResponse(target_date=target_date, language=language, cached=False, **data)

    row = LifeThemeCache(
        user_id=profile.user_id, target_date=target_date, language=language,
        birth_profile_version=profile.version, data=data,
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)
    return LifeThemeResponse(target_date=target_date, language=language, cached=was_race, **data)
