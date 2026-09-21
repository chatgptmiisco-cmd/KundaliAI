"""Prediction Engine: year-ahead / multi-year outlook (Varshaphala + running
dasha + transit doshas) and marriage-timing prediction (dasha/transit window
scan). Every fact here is computed from the person's real birth data — no
LLM call, no scraped/templated third-party content (see the Prediction
Engine plan). Both languages are computed and cached together, same
convention as every other cached artifact in this app.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Literal

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.charts import house_number, navamsa_sign_index, sign_index
from app.astro.constants import DAYS_PER_YEAR, PLANET_NAMES_EN, PLANET_NAMES_HI, PlanetKey
from app.astro.dasha import (
    Antardasha,
    Mahadasha,
    SubPeriod,
    compute_pratyantardashas,
    find_current_antardasha,
    find_current_mahadasha,
)
from app.astro.doshas import compute_dhaiya, compute_sade_sati
from app.astro.ephemeris import all_planet_positions, ascendant_sidereal, declination, julian_day_ut
from app.astro.event_karakas import CATEGORY_KARAKAS
from app.astro.event_window_scanner import _DASHA_RELATIONSHIP_MULTIPLIER, ScoredWindow, _dasha_relationship
from app.astro.life_event_timing import EventType
from app.astro.life_event_timing import EVENT_HOUSE as LIFE_EVENT_HOUSE
from app.astro.life_event_timing import EVENT_SECONDARY_HOUSES
from app.astro.life_event_timing import corroborate_with_transits as corroborate_life_event_with_transits
from app.astro.life_event_timing import event_rules, find_event_windows
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
from app.astro.property_analysis import (
    BPHS_48_2_4,
    PROPERTY_INTENT_REFRAME_INHERITANCE,
    PROPERTY_INTENT_REFRAME_RELOCATION,
    PROPERTY_INTENT_REFRAME_SALE,
    PROPERTY_KARAKA_MARS_SATURN,
    PROPERTY_TIMING_WINDOWS,
    compute_property_promise,
)
from app.astro.shadbala import MINIMUM_RUPAS, ShadbalaChartInputs, compute_all_shadbala, compute_time_of_day_facts
from app.astro.transit_corroboration import TransitCheck
from app.astro.transits import compute_transit_snapshot
from app.astro.varshaphala import compute_solar_return, compute_varshaphala
from app.astro.vargas import (
    chaturthamsa_sign_index,
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
from app.db.models.prediction_query_log import PredictionQueryLog
from app.schemas.prediction import (
    DecisionResponse,
    LifeEventTimingResponse,
    LifeThemeResponse,
    MarriageTimingResponse,
    MultiYearOutlookResponse,
    YearOutlookResponse,
)
from app.schemas.life_state import LifeStateOut
from app.schemas.property import (
    IMPLEMENTED_PROPERTY_INTENTS,
    PropertyAnalysis,
    PropertyD4Factors,
    PropertyFactors,
    PropertyIntent,
    PropertyPromise,
    PropertyRuleEvidence,
)
from app.schemas.user import BirthDataOut
from app.services.cache_utils import add_and_commit_or_fetch_existing
from app.services.chart_service import birth_datetime_utc, get_chart
from app.services.dasha_service import get_mahadashas_raw
from app.services.interpretation.base import Language
from app.services.interpretation.prediction_templates import (
    decision_reason_text,
    expecting_delivery_reason_text,
    life_event_reason_text,
    life_theme_text,
    marriage_window_reason_text,
    overall_year_theme,
    year_outlook_text,
)
from app.services.user_service import decrypt_life_state, get_life_state

Direction = Literal["past", "future"]
# How far ahead of "now" a future-direction search looks. Needs to be long
# enough to reach a target planet's own Antardasha even in the unlucky case
# where it just passed in the CURRENT Mahadasha and doesn't recur until deep
# into the NEXT one — worst case is close to (current Mahadasha's remaining
# length) + (most of the next Mahadasha's length), and the two longest
# Mahadashas (Venus 20y, Saturn 19y) can combine to nearly 35-40 years.
# Widened from 20.0 — found by comparing this engine's own output against
# independent chart reads: a chart's ONLY house-lord-level Antardasha for
# "children" (Jupiter, both the 5th lord and the classical karaka here) had
# already passed in early childhood (age ~9, hard-implausible) and didn't
# recur until age ~41.65 (a Jupiter Antardasha inside a later Saturn
# Mahadasha) — about 21.75 years after "now" (age ~19.9), just outside the
# old 20-year horizon. The engine fell back to a much weaker backdrop-only
# window instead, purely because the real answer was never in the search
# window at all, not because it was outranked. See _TIMING_ALGO_VERSION v16.
_FUTURE_HORIZON_YEARS = 30.0

# Default look-back for direction="past" — "what happened in my past" reads
# as "what happened recently," not "what's the single strongest period
# anywhere in my life, even in early childhood." Same "narrow, but never
# with a hard wall" lesson as _FUTURE_HORIZON_YEARS: if the recent-only
# search's best candidate is still hard-implausible-age or backdrop-only
# evidence, _resolve_past_windows falls back to the full birth-to-now
# lifetime instead of silently returning a weak recent answer when a much
# better one exists further back. See _TIMING_ALGO_VERSION v18.
_PAST_RECENCY_YEARS = 10.0

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
# v15: two presentation fixes requested after reviewing v14's output on a
# 20-chart QA set —
#   - a new `confidence` field ("strong"/"moderate"/"low", derived 1:1 from
#     evidence_level) so a "backdrop_only" window structurally reads as
#     low-confidence instead of like a normal prediction with a footnote.
#     The reason text for such a window now LEADS with that caveat (see
#     prediction_templates._weak_evidence_sentence) instead of only
#     appending it at the end, after an otherwise-confident-sounding
#     paragraph.
#   - marriage/children windows at a soft age boundary (age_implausibility
#     is "early"/"late" but still literal_event_plausible=True — a real,
#     if young/old, window) now also get an explicit "read this as
#     relationship/commitment (or family-planning) activation rather than
#     the literal date" note (see prediction_templates.
#     _soft_age_interpretation_sentence) — milder than the hard
#     reinterpretation sentence (literal_event_plausible=False), which
#     already covers the case where NO plausible-age window exists at all.
# v16: _FUTURE_HORIZON_YEARS widened from 20.0 to 30.0 — the fixed 20-year
# future search window could miss a genuinely well-evidenced Antardasha
# entirely (not just get outranked by one), if the target planet's own
# Antardasha didn't recur until slightly past that cutoff. Found by
# comparing this engine's own output against independent chart reads: one
# chart's children_timing "future" answer was a weak backdrop-only window
# (Jupiter Mahadasha, Sun Antardasha — Sun is neither the 5th lord nor a
# children karaka here) even though Jupiter IS both the 5th lord and the
# classical children karaka for that chart — its own Antardasha had already
# passed at age ~9 (hard-implausible) and didn't recur until age ~41.65
# (inside a later Saturn Mahadasha), about 21.75 years past "now" and just
# outside the old 20-year horizon. _select_candidate_pool's age-before-
# evidence priority (see v14) was working correctly on the candidates it
# was given — the real fix here is upstream, in what candidates the search
# horizon lets it see at all. See _FUTURE_HORIZON_YEARS's own comment for
# the worst-case Mahadasha-length reasoning behind picking 30.0.
# v17: companion fix to v16 — widening the horizon let several OTHER
# "future" answers jump from an already-strong near-term window to a
# merely-higher-scoring far-future one with the SAME evidence tier, since
# _rerank_with_transit_bonus/_select_candidate_pool only ever tie-broke by
# score, never recency. Found immediately after shipping v16, by diffing
# its output against the pre-v16 run: e.g. one chart's "when will my career
# improve" moved from age 45 to age 60, another's foreign-travel answer
# from age 52 to age 77, purely because the far window scored marginally
# higher (often just from its own transit corroboration) — a worse answer
# to "when," even though not a worse answer to "what's your single
# highest-scoring window ever." For direction="future" only, both functions
# now put the EARLIEST window ahead of raw/effective score WITHIN the same
# (is_hard_implausible, evidence_rank) bucket (see each function's
# docstring) — this only changes which window wins a tie inside a bucket
# v14 already established; it cannot make a lower-evidence or
# hard-implausible-age window win against a better one. direction="past"
# is unchanged (score-first) since "which past period was strongest" is a
# different question than "when will X next happen."
# v18: four changes from comparing engine output against a real user's
# actual life state, not just against independent chart reads —
#   - a user's optional LifeState (marital_status/marriage_date/
#     children_count/pregnancy_status/expected_delivery — see
#     app.db.models.life_state) now reframes marriage_timing/
#     life_event_timing(event_type="children") reason text when the
#     "first marriage"/"first child" question is already resolved (see
#     prediction_templates._already_married_sentence/
#     _already_has_children_sentence), and an already-expecting user's
#     FUTURE children query anchors directly to their own
#     expected_delivery instead of running a blind search that would
#     otherwise propose a nonsensical brand-new future window (see
#     _delivery_anchor_window). Cache rows now also key on
#     `life_state_version` (stored inside the JSON blob, same convention
#     as `algo_version`) so editing your life state invalidates stale
#     predictions without a cache-table migration.
#   - direction="past" now defaults to searching only _PAST_RECENCY_YEARS
#     instead of full birth-to-now, falling back to the full lifetime only
#     when the recent-only pool's best candidate is still hard-implausible
#     or backdrop-only (see _resolve_past_windows) — "what happened in my
#     past" reads as "what happened recently," not "what's the strongest
#     period anywhere in my life, even in early childhood."
#   - `long_term_peak` (see LongTermPeak/_find_long_term_peak) separately
#     surfaces the single highest-scoring plausible-age window in the
#     whole future search horizon when it's genuinely different from and
#     meaningfully stronger than `windows[0]` — restoring visibility into
#     what v17's earliest-wins-ties change intentionally stopped
#     defaulting to, instead of losing that information entirely.
#   - `peak_window` (see PeakWindow/_peak_window_for) narrows a window's
#     own Antardasha down to a tighter Pratyantardasha-level sub-range
#     when a real PD-level house-lord/karaka match exists — the PD math
#     already existed (app.astro.dasha.compute_pratyantardashas, used
#     elsewhere for "what's running right now") but was never wired into
#     window selection/presentation before.
# v19 (Phase 2 — event-specific sub-intents): ships the subset of the
# user's original ~20-sub-intent wishlist that's either explicitly spec'd
# by them or a direct, well-grounded reuse of houses/karakas this engine
# already computes — see the "iterative-strolling-truffle" plan for the
# full scoping rationale and what's deliberately still deferred.
#   - MarriageWindow gains `stage` ("marriage"/"serious_commitment"/
#     "relationship_stress") — no new astrology, relabels evidence_level/
#     transit_corroborated/transit_obstructed (already computed) into a
#     plain marriage-specific name — and `d9_confirmed`: whether the
#     window's own Antardasha lord is exalted/own-sign in the D9 (Navamsa)
#     chart, the classical marriage-confirmation chart, checked
#     independently of the D1 dasha math the window was already selected
#     from.
#   - LifeEventWindow gains `theme` (event_type="career" only):
#     "leadership_authority" when the Sun (career's existing "authority
#     and status" karaka) runs the window, "structural_change" when the
#     actual house lord does — a real distinction the reason text already
#     drew in prose, now also exposed as its own field.
#   - Three new event_type values via app.astro.life_event_timing's new
#     multi-house rule-set support (EVENT_SECONDARY_HOUSES): "career_promotion"
#     (10th+11th+2nd house lords, the user's own spec), "business_expansion"
#     (11th+2nd), and "business_partnership" (the 7th house's OTHER
#     classical meaning — all partnerships, not just marriage; Mercury as
#     trade/commerce karaka) — gated by the user's LifeState.business_state
#     so it doesn't return a generic 7th-house reading indistinguishable
#     from marriage_timing for someone with no stated business intent.
# v20 — no new astrology, plain-language pass over prediction_templates'
# natal-strength ("dignified, unafflicted"/"afflicted or debilitated" ->
# plain strong/weak wording) and transit-obstruction ("a real caution flag
# alongside the corroboration above, not a contradiction of it" -> a
# self-contained caution sentence that doesn't presuppose a corroboration
# sentence which may not even be present) reason-text sentences, plus
# career's karaka descriptions (untranslated "karaka"/"santan" -> "the
# classical significator for..."). Bumped purely so already-cached reason
# text (which bakes the old wording into the stored JSON) gets recomputed.
_TIMING_ALGO_VERSION = 20

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

Confidence = Literal["strong", "moderate", "low"]

# A plain-language confidence label derived 1:1 from evidence_level, so a
# consumer (chat, frontend) can decide how to present a window without
# re-deriving the evidence/reason-key logic itself — found by comparing
# this engine's own output against independent chart reads: a
# "backdrop_only" window (only tied to the event via its broader Mahadasha)
# was reading as a normal, confident prediction with nothing structurally
# marking it as weaker than a house-lord-level one.
_CONFIDENCE_FOR_EVIDENCE: dict[EvidenceLevel, Confidence] = {
    "house_lord_antardasha": "strong", "karaka_antardasha": "moderate", "backdrop_only": "low",
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
    windows: list[ScoredWindow], birth_dt: datetime, event_category: EventCategory, direction: Direction = "past"
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

    For `direction="future"`, the EARLIEST window within a `_pool_priority`
    bucket is kept ahead of a later one, even if the later one has a higher
    raw dasha score — see _rerank_with_transit_bonus's docstring for why
    (same reasoning, applied at this earlier candidate-pool stage so a
    near-term window with the right evidence tier can't be squeezed out of
    the pool entirely by several higher-scoring far-future ones before
    transit corroboration ever runs). `direction="past"` (the default) keeps
    the original score-ordered behavior — `windows` is assumed already
    sorted by raw score, and Python's sort is stable, so windows keep their
    relative raw-score order within each `_pool_priority` bucket; this
    re-orders buckets, it doesn't re-rank within one."""
    if direction == "future":
        ordered = sorted(windows, key=lambda w: (*_pool_priority(w, birth_dt, event_category), w.start))
    else:
        ordered = sorted(windows, key=lambda w: _pool_priority(w, birth_dt, event_category))
    return ordered[:_CANDIDATE_POOL_SIZE]


def _rerank_with_transit_bonus(
    scored_pairs: list[tuple[ScoredWindow, TransitCheck]],
    birth_dt: datetime,
    event_category: EventCategory,
    direction: Direction = "past",
) -> list[tuple[ScoredWindow, TransitCheck]]:
    """Re-sorts a (window, transit_check) pool by dasha score PLUS the
    Ashtakavarga-scaled corroboration bonus MINUS the obstruction-fraction
    penalty, scaled by real-world age plausibility (see _effective_score),
    then trims to the final count.

    For `direction="future"`, the EARLIEST window within a `_pool_priority`
    bucket wins outright — effective score only breaks a tie between two
    windows starting at literally the same moment — instead of `past`'s
    score-first order (score, then earliest start). Found by comparing this
    engine's own output against independent chart reads, right after
    widening _FUTURE_HORIZON_YEARS (see v16): several "future" answers
    jumped from an already-strong NEAR window to a merely-higher-scoring
    FAR one with the exact same evidence tier — e.g. one chart's "when will
    my career improve" moved from age 45 to age 60, another's foreign-travel
    answer from age 52 to age 77 — purely because the far window scored
    marginally higher (often just from its own transit corroboration),
    not because it was a meaningfully better answer to "when." A user
    asking "when will X happen" wants the next qualifying window, not the
    single highest-scoring one across their entire remaining life. `past`
    keeps score-first ordering since "which past period was strongest"
    really is asking for the best one, not the most recent.

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
    if direction == "future":
        scored_pairs.sort(
            key=lambda pair: (
                *_pool_priority(pair[0], birth_dt, event_category),
                pair[0].start,
                -_effective_score(pair[0], pair[1], birth_dt, event_category),
            )
        )
    else:
        scored_pairs.sort(
            key=lambda pair: (
                *_pool_priority(pair[0], birth_dt, event_category),
                -_effective_score(pair[0], pair[1], birth_dt, event_category),
                pair[0].start,
            )
        )
    return scored_pairs[:_FINAL_WINDOW_COUNT]


# How much higher a candidate's effective score must be than the primary
# window's to count as a genuinely different "long-term peak" rather than
# noise — see _find_long_term_peak. 20% is deliberately not tiny: v17
# already lets a much-higher-scoring SAME-tier window lose to an earlier
# one, so re-surfacing every marginal difference here would just recreate
# the "always show the highest score" behavior v17 fixed, one field over.
_LONG_TERM_PEAK_MARGIN = 1.2


def _find_long_term_peak(
    pairs: list[tuple[ScoredWindow, TransitCheck]],
    birth_dt: datetime,
    event_category: EventCategory,
    top_window: ScoredWindow,
) -> tuple[ScoredWindow, TransitCheck] | None:
    """The single highest-`_effective_score` candidate in the SAME
    (is_hard_implausible, evidence_rank) bucket as `top_window` — what
    `top_window` itself would have been before v17 made direction="future"
    prefer the earliest window in a bucket over the highest-scoring one.
    Returns None when there's nothing meaningfully better/different, so a
    boring chart doesn't get a redundant `long_term_peak` restating
    `windows[0]` — see MarriageWindow.peak_window's sibling,
    LongTermPeak, and `_LONG_TERM_PEAK_MARGIN`.

    Only meaningful for direction="future" — callers don't invoke this for
    "past" (see get_marriage_timing/get_life_event_timing)."""
    top_bucket = _pool_priority(top_window, birth_dt, event_category)
    same_bucket = [p for p in pairs if _pool_priority(p[0], birth_dt, event_category) == top_bucket]
    if len(same_bucket) < 2:
        return None

    top_pair = next((p for p in same_bucket if p[0] is top_window), None)
    if top_pair is None:
        return None
    top_score = _effective_score(top_pair[0], top_pair[1], birth_dt, event_category)

    best = max(same_bucket, key=lambda p: _effective_score(p[0], p[1], birth_dt, event_category))
    if best[0] is top_window or best[0].start == top_window.start:
        return None
    best_score = _effective_score(best[0], best[1], birth_dt, event_category)
    if top_score <= 0 or best_score < top_score * _LONG_TERM_PEAK_MARGIN:
        return None
    return best


def _find_source_antardasha(mahadashas: list[Mahadasha], window: ScoredWindow) -> Antardasha | None:
    """The real Antardasha `window` was scored from — needed to compute its
    Pratyantardashas (see _peak_window_for), since a ScoredWindow only
    keeps [start, end) already clipped to the search horizon, not a
    reference to the Antardasha object it came from."""
    for maha in mahadashas:
        if maha.lord != window.mahadasha_lord:
            continue
        for antar in maha.antardashas:
            if antar.lord == window.antardasha_lord and antar.start <= window.start < antar.end:
                return antar
    return None


def _delivery_anchor_window(mahadashas: list[Mahadasha], expected_delivery: datetime) -> ScoredWindow | None:
    """For a user already expecting (see LifeState.pregnancy_status), "when
    will I have a child?" is already resolved at the conception level —
    searching for a NEW blind future children window would be wrong.
    Anchors directly to whichever Antardasha already covers the user's own
    `expected_delivery` date and reports THAT as the family-adjustment
    window (see get_life_event_timing's `expecting_override` branch and
    expecting_delivery_reason_text) — score is irrelevant here (0.0):
    relevance comes from the user's own known life state, not dasha
    scoring, so it's never compared against other windows."""
    maha = find_current_mahadasha(mahadashas, expected_delivery)
    if maha is None:
        return None
    antar = find_current_antardasha(maha, expected_delivery)
    if antar is None:
        return None
    return ScoredWindow(
        start=antar.start, end=antar.end, mahadasha_lord=maha.lord, antardasha_lord=antar.lord,
        score=0.0, reason_keys=[],
    )


def _peak_window_for(
    mahadashas: list[Mahadasha], window: ScoredWindow, event_category: EventCategory, house_lord_planet: PlanetKey
) -> tuple[datetime, datetime] | None:
    """Light Pratyantardasha (PD) narrowing: re-scores `window`'s own
    Antardasha's 9 Pratyantardashas (app.astro.dasha.compute_pratyantardashas
    — already computed elsewhere for "what's running right now" via
    dasha_service.py, just never wired into window selection here) against
    the SAME house-lord/karaka test already used at the Antardasha level
    (see CATEGORY_KARAKAS), and returns the narrower [start, end) actually
    covered by a real PD-level match — e.g. a few-month-wide "peak
    commitment window" inside a multi-year "relationship activation"
    window, the level of precision needed before a user says "wait, I
    actually got married in November 2024."

    Purely additive/presentational — does NOT change which Antardasha won
    selection (still decided entirely by _pool_priority/_effective_score,
    unchanged). Returns None when there's no PD-level match, or when the
    "narrowed" range would be the whole window anyway (no real narrowing)."""
    antar = _find_source_antardasha(mahadashas, window)
    if antar is None:
        return None

    sub_periods = compute_pratyantardashas(antar)
    relevant_lords = {house_lord_planet, *CATEGORY_KARAKAS.get(event_category, ())}
    matching = [
        (max(sp.start, window.start), min(sp.end, window.end))
        for sp in sub_periods
        if sp.lord in relevant_lords and sp.start < window.end and sp.end > window.start
    ]
    if not matching or len(matching) == len(sub_periods):
        return None

    start = min(s for s, _ in matching)
    end = max(e for _, e in matching)
    if start <= window.start and end >= window.end:
        return None
    return start, end


def _search_bounds(
    direction: Direction,
    birth_dt: datetime,
    now: datetime,
    mahadashas: list[Mahadasha] | None = None,
    *,
    past_full_lifetime: bool = False,
) -> tuple[datetime, float]:
    """Where to point the window scanner — a recency-limited or (with
    `past_full_lifetime=True`) full birth-to-now past search, or a
    forward-looking horizon out to +_FUTURE_HORIZON_YEARS from now. Same
    scanner (app.astro.event_window_scanner.scan_dasha_windows) either way;
    this is purely a different choice of bounds, not new astro logic.

    For "past" (`past_full_lifetime=False`, the default), searches only the
    last _PAST_RECENCY_YEARS — "what happened in my past" reads as "what
    happened recently," not "what's the strongest period anywhere in my
    life, even in early childhood." `past_full_lifetime=True` searches the
    entire birth-to-now span instead; see _resolve_past_windows for when
    each is used (recency first, full lifetime as a fallback).

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
    backward, so the search still reaches +_FUTURE_HORIZON_YEARS from `now`,
    not from this earlier start."""
    if direction == "past":
        age_years = max((now - birth_dt).days / DAYS_PER_YEAR, 0.0)
        if past_full_lifetime:
            return birth_dt, age_years
        recency_years = min(_PAST_RECENCY_YEARS, age_years)
        from_dt = now - timedelta(days=recency_years * DAYS_PER_YEAR)
        return from_dt, recency_years

    from_dt = now
    if mahadashas is not None:
        current_maha = find_current_mahadasha(mahadashas, now)
        current_antar = find_current_antardasha(current_maha, now) if current_maha is not None else None
        if current_antar is not None:
            from_dt = current_antar.start
    horizon_years = _FUTURE_HORIZON_YEARS + (now - from_dt).days / DAYS_PER_YEAR
    return from_dt, horizon_years


def _resolve_past_windows(
    direction: Direction,
    birth_dt: datetime,
    now: datetime,
    mahadashas: list[Mahadasha] | None,
    event_category: EventCategory,
    scan_and_select: Callable[[datetime, float], list[ScoredWindow]],
) -> list[ScoredWindow]:
    """Runs `scan_and_select(from_dt, horizon_years)` with the bounds
    `_search_bounds` picks for `direction`, applying the recency-default/
    full-lifetime-fallback only for direction="past" (see
    _PAST_RECENCY_YEARS and _search_bounds' docstring) — "future" just
    delegates straight through with a single call.

    The fallback check mirrors _pool_priority's own bucket test (hard-
    implausible-age, then backdrop-only) rather than a score threshold:
    if the recency-limited search's top pick is already a real,
    plausible-age, non-backdrop window, a genuinely stronger CANDIDATE
    further back wouldn't change the right answer to "what happened
    recently" anyway — only re-scan the full lifetime when the recent-only
    pool couldn't find anything better than that."""
    from_dt, horizon_years = _search_bounds(direction, birth_dt, now, mahadashas)
    candidates = scan_and_select(from_dt, horizon_years)
    if direction != "past":
        return candidates

    top = candidates[0] if candidates else None
    recent_pool_is_weak = top is None or _is_hard_implausible(top, birth_dt, event_category) or (
        _evidence_level(top) == "backdrop_only"
    )
    if not recent_pool_is_weak:
        return candidates

    full_from_dt, full_horizon_years = _search_bounds(direction, birth_dt, now, mahadashas, past_full_lifetime=True)
    return scan_and_select(full_from_dt, full_horizon_years)


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
    life_state_row = await get_life_state(db, profile.user_id)
    life_state = decrypt_life_state(life_state_row) if life_state_row else None
    life_state_version = life_state.version if life_state else 0

    select_stmt = _marriage_select_stmt(profile, direction, language)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if (
        cached_row is not None
        and all(k in cached_row.data for k in _REQUIRED_CACHE_KEYS)
        and cached_row.data.get("algo_version") == _TIMING_ALGO_VERSION
        and cached_row.data.get("life_state_version") == life_state_version
    ):
        await log_prediction_query(
            db, profile.user_id, "marriage_timing", direction, language,
            _timing_result_summary(cached_row.data.get("windows", [])),
        )
        return MarriageTimingResponse(language=language, direction=direction, cached=True, **cached_row.data)

    d1 = await get_chart(db, profile, birth, "D1")
    d9 = await get_chart(db, profile, birth, "D9")
    d9_dignity = {p.planet: p.dignity for p in d9.planets}
    moon = next(p for p in d1.planets if p.planet == "Mo")
    mars = next(p for p in d1.planets if p.planet == "Ma")
    mahadashas = await get_mahadashas_raw(db, profile, birth)
    seventh_lord = house_lord(7, d1.lagna_sign_index)
    birth_dt = birth_datetime_utc(birth)
    now = datetime.now(timezone.utc)
    strength = await _get_cached_significator_strength(db, profile, birth, d1)
    retrograde = _significator_retrograde(d1)
    natal_planet_sign = _natal_planet_sign_index(d1)

    def _compute_windows():
        def scan_and_select(from_dt: datetime, horizon_years: float) -> list[ScoredWindow]:
            raw_windows = find_marriage_windows(
                mahadashas, seventh_lord, from_dt, horizon_years, top_n=_RAW_SCAN_POOL_SIZE, strength=strength
            )
            return _select_candidate_pool(raw_windows, birth_dt, "marriage", direction)

        windows = _resolve_past_windows(direction, birth_dt, now, mahadashas, "marriage", scan_and_select)
        pairs = [
            (w, corroborate_with_transits(w, d1.lagna_sign_index, moon.sign_index, natal_planet_sign))
            for w in windows
        ]
        scored_windows = _rerank_with_transit_bonus(pairs, birth_dt, "marriage", direction)
        long_term_peak_pair = None
        if direction == "future" and scored_windows:
            long_term_peak_pair = _find_long_term_peak(pairs, birth_dt, "marriage", scored_windows[0][0])
        return scored_windows, long_term_peak_pair

    scored_windows, long_term_peak_pair = await anyio.to_thread.run_sync(_compute_windows)

    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
    seventh_lord_name = names[seventh_lord]
    already_married = life_state is not None and life_state.marital_status == "married"
    marriage_date_str = life_state.marriage_date.isoformat() if life_state and life_state.marriage_date else None
    windows_out = []
    for w, check in scored_windows:
        age_years = (w.start - birth_dt).days / DAYS_PER_YEAR
        age_multiplier = age_plausibility_multiplier("marriage", age_years)
        literal_event_plausible = not is_hard_implausible_age("marriage", age_years)
        evidence_level = _evidence_level(w)
        d9_confirmed = d9_dignity.get(w.antardasha_lord) in ("exalted", "own_sign")
        # `check.obstructed` alone (see app.astro.transit_corroboration) is
        # True from even a single sampled point (of 3: start/mid/end) under
        # a malefic transit — deliberately sensitive for the continuous
        # score penalty (`check.obstruction_fraction` scales it), but WAY
        # too noisy as a binary "this is a stress period" label: a
        # majority of a chart's own windows have SOME momentary obstruction
        # somewhere in a multi-year span. `relationship_stress` needs the
        # MAJORITY of sampled points obstructed, not just one.
        stage = (
            "relationship_stress" if check.obstruction_fraction >= 0.5
            else "marriage" if evidence_level == "house_lord_antardasha" and check.corroborated
            else "serious_commitment"
        )
        reason = marriage_window_reason_text(
            w.reason_keys, seventh_lord_name, w.antardasha_lord, check.corroborated, language, tense=direction,
            natal_strength=_natal_strength_category(strength.get(w.antardasha_lord, 1.0)),
            antardasha_lord_retrograde=retrograde.get(w.antardasha_lord, False),
            transit_obstructing_planet=names[check.obstructing_planet] if check.obstructing_planet else None,
            age_implausibility=is_implausible_age("marriage", age_years),
            literal_event_plausible=literal_event_plausible,
            evidence_level=evidence_level,
            already_married=already_married,
            marriage_date=marriage_date_str,
            d9_confirmed=d9_confirmed,
        )
        peak_window = _peak_window_for(mahadashas, w, "marriage", seventh_lord)
        peak_window_out = None
        if peak_window is not None:
            pw_start, pw_end = peak_window
            peak_window_out = {"start_date": pw_start.date().isoformat(), "end_date": pw_end.date().isoformat()}
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
                "peak_window": peak_window_out,
                "transit_corroborated": check.corroborated,
                "transit_corroboration_strength": check.corroboration_strength,
                "transit_obstructed": check.obstructed,
                "transit_obstruction_fraction": check.obstruction_fraction,
                "age_plausibility_multiplier": age_multiplier,
                "literal_event_plausible": literal_event_plausible,
                "evidence_level": evidence_level,
                "confidence": _CONFIDENCE_FOR_EVIDENCE[evidence_level],
                "stage": stage,
                "d9_confirmed": d9_confirmed,
            }
        )

    long_term_peak_out = None
    if long_term_peak_pair is not None:
        peak_w, _peak_check = long_term_peak_pair
        long_term_peak_out = {
            "start_date": peak_w.start.date().isoformat(),
            "end_date": peak_w.end.date().isoformat(),
            "mahadasha_lord": peak_w.mahadasha_lord,
            "mahadasha_lord_name": names[peak_w.mahadasha_lord],
            "antardasha_lord": peak_w.antardasha_lord,
            "antardasha_lord_name": names[peak_w.antardasha_lord],
            "score": peak_w.score,
        }

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

    data = {
        "windows": windows_out,
        "manglik_note": manglik_note,
        "long_term_peak": long_term_peak_out,
        "algo_version": _TIMING_ALGO_VERSION,
        "life_state_version": life_state_version,
    }

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        await log_prediction_query(
            db, profile.user_id, "marriage_timing", direction, language, _timing_result_summary(windows_out)
        )
        return MarriageTimingResponse(language=language, direction=direction, cached=False, **data)

    row = MarriageTimingCache(
        user_id=profile.user_id, direction=direction, language=language, birth_profile_version=profile.version,
        data=data,
    )
    data, was_race = await add_and_commit_or_fetch_existing(db, row, select_stmt)
    await log_prediction_query(
        db, profile.user_id, "marriage_timing", direction, language, _timing_result_summary(data.get("windows", []))
    )
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
    life_state_row = await get_life_state(db, profile.user_id)
    life_state = decrypt_life_state(life_state_row) if life_state_row else None
    life_state_version = life_state.version if life_state else 0

    select_stmt = _life_event_select_stmt(profile, event_type, direction, language)
    result = await db.execute(select_stmt)
    cached_row = result.scalar_one_or_none()
    if (
        cached_row is not None
        and all(k in cached_row.data for k in _REQUIRED_CACHE_KEYS)
        and cached_row.data.get("algo_version") == _TIMING_ALGO_VERSION
        and cached_row.data.get("life_state_version") == life_state_version
    ):
        await log_prediction_query(
            db, profile.user_id, event_type, direction, language,
            _timing_result_summary(cached_row.data.get("windows", [])),
        )
        return LifeEventTimingResponse(
            event_type=event_type, language=language, direction=direction, cached=True, **cached_row.data
        )

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    mahadashas = await get_mahadashas_raw(db, profile, birth)
    house_lord_planet = house_lord(LIFE_EVENT_HOUSE[event_type], d1.lagna_sign_index)
    secondary_lords = {
        house: house_lord(house, d1.lagna_sign_index) for house, _ in EVENT_SECONDARY_HOUSES.get(event_type, [])
    }
    birth_dt = birth_datetime_utc(birth)
    now = datetime.now(timezone.utc)
    strength = await _get_cached_significator_strength(db, profile, birth, d1)
    retrograde = _significator_retrograde(d1)
    natal_planet_sign = _natal_planet_sign_index(d1)
    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN
    house_lord_name = names[house_lord_planet]

    # Phase 2: business_partnership reuses the 7th house's OTHER classical
    # meaning (all partnerships, not just marriage) — without a life-state
    # gate, it would return a generic 7th-house reading indistinguishable
    # from marriage_timing for anyone, regardless of whether business is
    # even relevant to them.
    business_partnership_blocked = event_type == "business_partnership" and not (
        life_state is not None and life_state.business_state in ("running", "considering")
    )

    # A promotion presupposes an existing job — without this gate, someone
    # who isn't even employed (or hasn't told us either way) gets the exact
    # same 10th-house dasha reading as someone asking a genuinely answerable
    # promotion question, with no acknowledgment that the premise itself is
    # unconfirmed. Same precedent as business_partnership_blocked above.
    career_promotion_blocked = event_type == "career_promotion" and not (
        life_state is not None and life_state.career_state == "employed"
    )

    # Already expecting, with a known due date: "when will I have a child?"
    # is already resolved at the conception level — searching for a NEW
    # blind future window would be wrong. Anchor directly to whichever
    # Antardasha already covers `expected_delivery` instead of scoring
    # candidates at all. See _delivery_anchor_window.
    expecting_override = (
        event_type == "children"
        and direction == "future"
        and life_state is not None
        and life_state.pregnancy_status == "expecting"
        and life_state.expected_delivery is not None
    )

    note_out = None
    if business_partnership_blocked:
        windows_out = []
        long_term_peak_out = None
        note_out = (
            "अपनी व्यावसायिक स्थिति प्रोफ़ाइल में सेट करें ताकि व्यापार-साझेदारी की समयावधि मिल सके।"
            if language == "hi" else
            "Set your business status in your profile to get business-partnership timing."
        )
    elif career_promotion_blocked:
        windows_out = []
        long_term_peak_out = None
        note_out = (
            "पदोन्नति का समय बताने से पहले मुझे यह जानना होगा — क्या आप अभी नौकरी में हैं? अपनी करियर स्थिति "
            "प्रोफ़ाइल में सेट करें, फिर मैं आपके लिए असली पदोन्नति समयावधि निकाल सकता/सकती हूं।"
            if language == "hi" else
            "Before I can talk about promotion timing — are you currently employed? Set your career status in "
            "your profile and I can give you a real read on this."
        )
    elif expecting_override:
        expected_delivery_dt = datetime.combine(life_state.expected_delivery, datetime.min.time(), timezone.utc)
        anchor = _delivery_anchor_window(mahadashas, expected_delivery_dt)
        long_term_peak_out = None
        if anchor is None:
            windows_out = []
        else:
            # No PD narrowing here: this window is anchored to the user's
            # OWN known expected_delivery date, not to wherever a PD-level
            # house-lord/karaka match happens to fall — narrowing to a
            # sub-range that doesn't even cover expected_delivery would be
            # actively misleading (see _delivery_anchor_window's docstring).
            peak_window_out = None
            reason = expecting_delivery_reason_text(anchor.antardasha_lord, life_state.expected_delivery.isoformat(), language)
            age_years = (anchor.start - birth_dt).days / DAYS_PER_YEAR
            windows_out = [
                {
                    "start_date": anchor.start.date().isoformat(),
                    "end_date": anchor.end.date().isoformat(),
                    "mahadasha_lord": anchor.mahadasha_lord,
                    "mahadasha_lord_name": names[anchor.mahadasha_lord],
                    "antardasha_lord": anchor.antardasha_lord,
                    "antardasha_lord_name": names[anchor.antardasha_lord],
                    "score": anchor.score,
                    "reason": reason,
                    "peak_window": peak_window_out,
                    "transit_corroborated": False,
                    "transit_corroboration_strength": 1.0,
                    "transit_obstructed": False,
                    "transit_obstruction_fraction": 0.0,
                    "age_plausibility_multiplier": age_plausibility_multiplier(event_type, age_years),
                    "literal_event_plausible": True,
                    "evidence_level": "house_lord_antardasha",
                    "confidence": "strong",
                }
            ]
    else:
        def _compute_windows() -> tuple[list[tuple[ScoredWindow, TransitCheck]], tuple[ScoredWindow, TransitCheck] | None]:
            def scan_and_select(from_dt: datetime, horizon_years: float) -> list[ScoredWindow]:
                raw_windows = find_event_windows(
                    mahadashas, event_type, house_lord_planet, from_dt, horizon_years,
                    top_n=_RAW_SCAN_POOL_SIZE, strength=strength, secondary_lords=secondary_lords,
                )
                return _select_candidate_pool(raw_windows, birth_dt, event_type, direction)

            windows = _resolve_past_windows(direction, birth_dt, now, mahadashas, event_type, scan_and_select)
            pairs = [
                (
                    w,
                    corroborate_life_event_with_transits(
                        event_type, w, d1.lagna_sign_index, moon.sign_index, natal_planet_sign
                    ),
                )
                for w in windows
            ]
            scored_windows = _rerank_with_transit_bonus(pairs, birth_dt, event_type, direction)
            long_term_peak_pair = None
            if direction == "future" and scored_windows:
                long_term_peak_pair = _find_long_term_peak(pairs, birth_dt, event_type, scored_windows[0][0])
            return scored_windows, long_term_peak_pair

        scored_windows, long_term_peak_pair = await anyio.to_thread.run_sync(_compute_windows)

        already_has_children = life_state is not None and life_state.children_count > 0 and not (
            life_state.pregnancy_status == "expecting"
        )
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
                already_has_children=already_has_children,
            )
            peak_window = _peak_window_for(mahadashas, w, event_type, house_lord_planet)
            peak_window_out = None
            if peak_window is not None:
                pw_start, pw_end = peak_window
                peak_window_out = {"start_date": pw_start.date().isoformat(), "end_date": pw_end.date().isoformat()}
            theme = None
            if event_type == "career":
                if w.antardasha_lord == "Su":
                    theme = "leadership_authority"
                elif w.antardasha_lord == house_lord_planet:
                    theme = "structural_change"
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
                    "peak_window": peak_window_out,
                    "transit_corroborated": check.corroborated,
                    "transit_corroboration_strength": check.corroboration_strength,
                    "transit_obstructed": check.obstructed,
                    "transit_obstruction_fraction": check.obstruction_fraction,
                    "age_plausibility_multiplier": age_multiplier,
                    "literal_event_plausible": literal_event_plausible,
                    "evidence_level": evidence_level,
                    "confidence": _CONFIDENCE_FOR_EVIDENCE[evidence_level],
                    "theme": theme,
                }
            )

        long_term_peak_out = None
        if long_term_peak_pair is not None:
            peak_w, _peak_check = long_term_peak_pair
            long_term_peak_out = {
                "start_date": peak_w.start.date().isoformat(),
                "end_date": peak_w.end.date().isoformat(),
                "mahadasha_lord": peak_w.mahadasha_lord,
                "mahadasha_lord_name": names[peak_w.mahadasha_lord],
                "antardasha_lord": peak_w.antardasha_lord,
                "antardasha_lord_name": names[peak_w.antardasha_lord],
                "score": peak_w.score,
            }

    data = {
        "windows": windows_out,
        "long_term_peak": long_term_peak_out,
        "note": note_out,
        "algo_version": _TIMING_ALGO_VERSION,
        "life_state_version": life_state_version,
    }

    if cached_row is not None:
        cached_row.data = data
        await db.commit()
        await log_prediction_query(
            db, profile.user_id, event_type, direction, language, _timing_result_summary(windows_out)
        )
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
    await log_prediction_query(
        db, profile.user_id, event_type, direction, language, _timing_result_summary(data.get("windows", []))
    )
    return LifeEventTimingResponse(
        event_type=event_type, language=language, direction=direction, cached=was_race, **data
    )


async def log_prediction_query(
    db: AsyncSession, user_id: str, intent: str, direction: str | None, language: Language, result_summary: dict
) -> None:
    """Appends one row to the user's Prediction Engine question/answer
    history (see app.db.models.prediction_query_log.PredictionQueryLog) —
    called for EVERY call to marriage-timing/life-event-timing/decision,
    cached or freshly computed, since this is meant to be a real usage
    history a later question can draw on (see get_decision's history-nudge
    logic), not just a cache-miss log. `result_summary` is a small
    structured dict (top window dates/score/evidence_level, or a
    decision's verdict/current-period-start) — never the full response."""
    db.add(
        PredictionQueryLog(
            user_id=user_id, intent=intent, direction=direction, language=language, result_summary=result_summary
        )
    )
    await db.commit()


def _timing_result_summary(windows_out: list[dict]) -> dict:
    """Small structured summary of a marriage-timing/life-event-timing
    response for PredictionQueryLog — just the top window's key facts, not
    the full payload (reason text, all 3 windows, etc.)."""
    if not windows_out:
        return {"top_window_start": None}
    top = windows_out[0]
    return {"top_window_start": top["start_date"], "score": top["score"], "evidence_level": top["evidence_level"]}


_DUSTHANA_HOUSES = (6, 8, 12)


def _dusthana_lords(lagna_sign_index: int) -> set[PlanetKey]:
    """The 6th/8th/12th house lords from lagna — the classical dusthana
    (difficulty) houses. Their own Antardashas are the traditional "expect
    friction or disruption" signal, independent of which specific decision
    is being asked about — see _is_currently_dusthana_afflicted."""
    return {house_lord(house, lagna_sign_index) for house in _DUSTHANA_HOUSES}


def _is_currently_dusthana_afflicted(mahadashas: list[Mahadasha], now: datetime, dusthana_lords: set[PlanetKey]) -> bool:
    current_maha = find_current_mahadasha(mahadashas, now)
    if current_maha is None:
        return False
    current_antar = find_current_antardasha(current_maha, now)
    if current_antar is None:
        return False
    return current_antar.lord in dusthana_lords


def _current_period_score(
    mahadashas: list[Mahadasha],
    now: datetime,
    event_type: EventType,
    house_lord_planet: PlanetKey,
    strength: dict[PlanetKey, float],
    secondary_lords: dict[int, PlanetKey] | None = None,
) -> ScoredWindow | None:
    """Scores the Antardasha covering "now" using the exact SAME classical
    rule set (event_rules) and dasha-relationship weighting
    (_DASHA_RELATIONSHIP_MULTIPLIER) already applied to every full-horizon
    scan (see app.astro.event_window_scanner.scan_dasha_windows) — just
    evaluated for the one window containing "now" instead of a ranked
    search, so a decision about "right now" can be compared apples-to-
    apples against the near-term alternative windows those scans return.
    Returns None when no rule matches at all (score would be 0) — a
    decision has nothing to say about a period with zero classical tie to
    the event."""
    current_maha = find_current_mahadasha(mahadashas, now)
    if current_maha is None:
        return None
    current_antar = find_current_antardasha(current_maha, now)
    if current_antar is None:
        return None

    score = 0.0
    reason_keys: list[str] = []
    for rule in event_rules(event_type, house_lord_planet, strength, secondary_lords):
        lord = current_antar.lord if rule.applies_to == "antardasha_lord" else current_maha.lord
        if lord == rule.target:
            score += rule.weight
            reason_keys.append(rule.reason_key)
    if score <= 0:
        return None
    relationship = _dasha_relationship(current_maha.lord, current_antar.lord)
    score *= _DASHA_RELATIONSHIP_MULTIPLIER[relationship]

    return ScoredWindow(
        start=current_antar.start, end=current_antar.end,
        mahadasha_lord=current_maha.lord, antardasha_lord=current_antar.lord,
        score=score, reason_keys=reason_keys,
    )


# How much higher the best near-term future window's score must be than
# the current period's to count as "wait for it" rather than noise — same
# convention/value as _LONG_TERM_PEAK_MARGIN (Phase 1), reused here for the
# same reason: re-surfacing every marginal difference would make "should I
# do X now" flip-flop on tiny score deltas instead of a real signal.
_DECISION_NEAR_TERM_HORIZON_YEARS = 5.0
_DECISION_WAIT_MAX_YEARS_AWAY = 3.0

def _history_nudge(
    verdict: Literal["favorable", "unfavorable", "wait_for_better_window", "neutral"], prior_verdicts: list[str | None]
) -> Literal["favorable", "unfavorable"] | None:
    """Only ever nudges a "neutral" verdict — a clear favorable/
    unfavorable/wait_for_better_window signal from the chart is NEVER
    touched by history, per the explicit choice this was built to (history
    corroborates a borderline reading, it doesn't override a real one).
    Requires the last exactly-2 prior logged verdicts for this same
    decision_type to AGREE with each other and be a real, non-neutral
    verdict — a single prior data point, or two that disagree, isn't
    "consistent" enough to nudge anything."""
    if verdict != "neutral":
        return None
    if len(prior_verdicts) == 2 and prior_verdicts[0] == prior_verdicts[1] and prior_verdicts[0] in (
        "favorable", "unfavorable"
    ):
        return prior_verdicts[0]
    return None


_DECISION_EVENT_TYPE: dict[str, EventType] = {
    "job_change": "career_promotion", "business_start": "business_partnership", "house_purchase": "property",
}
_DECISION_HOUSE: dict[str, int] = {"job_change": 10, "business_start": 7, "house_purchase": 4}


async def get_decision(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut,
    decision_type: Literal["job_change", "business_start", "house_purchase"],
    language: Language,
) -> DecisionResponse:
    """Answers "should I do X now?" with a verdict (favorable/unfavorable/
    wait_for_better_window/neutral), not a list of windows — see the
    "iterative-strolling-truffle" plan (Phase 3) for the full design
    rationale. Not cached (unlike the other timing endpoints): "now" is
    inherent to the question, so re-running this cheap, already-cached-
    mahadasha-based computation is safer than serving a stale verdict for
    weeks."""
    life_state_row = await get_life_state(db, profile.user_id)
    life_state = decrypt_life_state(life_state_row) if life_state_row else None

    if decision_type == "business_start" and not (
        life_state is not None and life_state.business_state in ("running", "considering")
    ):
        note = (
            "अपनी व्यावसायिक स्थिति प्रोफ़ाइल में सेट करें ताकि यह निर्णय सुझाव मिल सके।" if language == "hi" else
            "Set your business status in your profile to get this decision's guidance."
        )
        await log_prediction_query(
            db, profile.user_id, f"{decision_type}_decision", None, language, {"verdict": None, "blocked": True}
        )
        return DecisionResponse(decision_type=decision_type, language=language, verdict="neutral", reasoning=note, note=note)

    d1 = await get_chart(db, profile, birth, "D1")
    moon = next(p for p in d1.planets if p.planet == "Mo")
    mahadashas = await get_mahadashas_raw(db, profile, birth)
    birth_dt = birth_datetime_utc(birth)
    now = datetime.now(timezone.utc)
    strength = await _get_cached_significator_strength(db, profile, birth, d1)
    natal_planet_sign = _natal_planet_sign_index(d1)
    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN

    event_type = _DECISION_EVENT_TYPE[decision_type]
    house_lord_planet = house_lord(_DECISION_HOUSE[decision_type], d1.lagna_sign_index)
    secondary_lords = {
        house: house_lord(house, d1.lagna_sign_index) for house, _ in EVENT_SECONDARY_HOUSES.get(event_type, [])
    }
    dusthana_lords = _dusthana_lords(d1.lagna_sign_index)

    def _compute() -> tuple[ScoredWindow | None, bool, tuple[ScoredWindow, TransitCheck] | None]:
        current = _current_period_score(mahadashas, now, event_type, house_lord_planet, strength, secondary_lords)
        afflicted = _is_currently_dusthana_afflicted(mahadashas, now, dusthana_lords)

        raw_windows = find_event_windows(
            mahadashas, event_type, house_lord_planet, now, _DECISION_NEAR_TERM_HORIZON_YEARS,
            top_n=_RAW_SCAN_POOL_SIZE, strength=strength, secondary_lords=secondary_lords,
        )
        pool = _select_candidate_pool(raw_windows, birth_dt, event_type, "future")
        pairs = [
            (w, corroborate_life_event_with_transits(event_type, w, d1.lagna_sign_index, moon.sign_index, natal_planet_sign))
            for w in pool
        ]
        ranked = _rerank_with_transit_bonus(pairs, birth_dt, event_type, "future")
        best_future = ranked[0] if ranked else None
        return current, afflicted, best_future

    current_period, dusthana_afflicted, best_future_pair = await anyio.to_thread.run_sync(_compute)

    better_window = None
    if best_future_pair is not None:
        best_w, best_check = best_future_pair
        current_score = current_period.score if current_period is not None else 0.0
        years_away = (best_w.start - now).days / DAYS_PER_YEAR
        if (
            years_away <= _DECISION_WAIT_MAX_YEARS_AWAY
            and _effective_score(best_w, best_check, birth_dt, event_type) >= max(current_score, 0.01) * _LONG_TERM_PEAK_MARGIN
        ):
            better_window = best_w

    current_evidence = _evidence_level(current_period) if current_period is not None else None
    if dusthana_afflicted:
        verdict: Literal["favorable", "unfavorable", "wait_for_better_window", "neutral"] = "unfavorable"
    elif current_period is not None and current_evidence in ("house_lord_antardasha", "karaka_antardasha") and better_window is None:
        verdict = "favorable"
    elif better_window is not None:
        verdict = "wait_for_better_window"
    else:
        verdict = "neutral"

    prior_rows = []
    if verdict == "neutral":
        result = await db.execute(
            select(PredictionQueryLog)
            .where(
                PredictionQueryLog.user_id == profile.user_id,
                PredictionQueryLog.intent == f"{decision_type}_decision",
            )
            .order_by(PredictionQueryLog.created_at.desc())
            .limit(2)
        )
        prior_rows = result.scalars().all()
    prior_verdicts = [row.result_summary.get("verdict") for row in prior_rows]
    history_nudge = _history_nudge(verdict, prior_verdicts)
    history_dates = [row.created_at.date().isoformat() for row in prior_rows] if history_nudge is not None else []

    current_period_out = None
    if current_period is not None:
        current_period_out = {
            "start_date": current_period.start.date().isoformat(),
            "end_date": current_period.end.date().isoformat(),
            "mahadasha_lord": current_period.mahadasha_lord,
            "mahadasha_lord_name": names[current_period.mahadasha_lord],
            "antardasha_lord": current_period.antardasha_lord,
            "antardasha_lord_name": names[current_period.antardasha_lord],
            "score": current_period.score,
            "evidence_level": current_evidence,
            "dusthana_afflicted": dusthana_afflicted,
        }
    better_window_out = None
    if better_window is not None:
        better_window_out = {
            "start_date": better_window.start.date().isoformat(),
            "end_date": better_window.end.date().isoformat(),
            "mahadasha_lord": better_window.mahadasha_lord,
            "mahadasha_lord_name": names[better_window.mahadasha_lord],
            "antardasha_lord": better_window.antardasha_lord,
            "antardasha_lord_name": names[better_window.antardasha_lord],
            "score": better_window.score,
        }

    reasoning = decision_reason_text(
        decision_type, verdict, language,
        current_period_lord=current_period.antardasha_lord if current_period else None,
        dusthana_afflicted=dusthana_afflicted,
        better_window_start=better_window.start.date().isoformat() if better_window else None,
        history_nudge=history_nudge,
        history_dates=history_dates,
    )

    await log_prediction_query(
        db, profile.user_id, f"{decision_type}_decision", None, language,
        {
            "verdict": verdict,
            "current_period_start": current_period.start.date().isoformat() if current_period else None,
        },
    )

    return DecisionResponse(
        decision_type=decision_type, language=language, verdict=verdict, reasoning=reasoning,
        current_period=current_period_out, better_window=better_window_out, history_nudge=history_nudge,
    )


async def get_marriage_decision(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, language: Language,
) -> DecisionResponse:
    """"Should I get married now" — deliberately NOT routed through
    get_decision's generic `_DECISION_EVENT_TYPE`/`_DECISION_HOUSE` machinery
    the way job_change/business_start/house_purchase are. Marriage already
    has its OWN dedicated, separately-vetted window computation
    (get_marriage_timing -> app.astro.marriage_timing.find_marriage_windows,
    with its own evidence levels and `stage`), and routing it through the
    generic path too would mean a SECOND, parallel marriage-timing
    computation that could disagree with the one marriage_timing_windows
    already relies on. This is a thin translation layer over that single
    existing source of truth instead — zero changes to get_decision itself."""
    life_state_row = await get_life_state(db, profile.user_id)
    life_state = decrypt_life_state(life_state_row) if life_state_row else None
    if life_state is not None and life_state.marital_status == "married":
        note = (
            "आप पहले से ही विवाहित हैं — यह सवाल अब लागू नहीं होता।" if language == "hi" else
            "You're already married — this decision doesn't apply anymore."
        )
        await log_prediction_query(
            db, profile.user_id, "marriage_decision", None, language, {"verdict": None, "blocked": True}
        )
        return DecisionResponse(decision_type="marriage", language=language, verdict="neutral", reasoning=note, note=note)

    timing = await get_marriage_timing(db, profile, birth, language, "future")
    now = datetime.now(timezone.utc).date()
    current_window = next((w for w in timing.windows if w.start_date <= now <= w.end_date), None)
    dusthana_afflicted = current_window is not None and current_window.stage == "relationship_stress"

    if dusthana_afflicted:
        verdict: Literal["favorable", "unfavorable", "wait_for_better_window", "neutral"] = "unfavorable"
    elif current_window is not None and current_window.evidence_level in ("house_lord_antardasha", "karaka_antardasha"):
        verdict = "favorable"
    elif timing.windows:
        verdict = "wait_for_better_window"
    else:
        verdict = "neutral"

    current_period_out = None
    if current_window is not None:
        current_period_out = {
            "start_date": current_window.start_date, "end_date": current_window.end_date,
            "mahadasha_lord": current_window.mahadasha_lord, "mahadasha_lord_name": current_window.mahadasha_lord_name,
            "antardasha_lord": current_window.antardasha_lord, "antardasha_lord_name": current_window.antardasha_lord_name,
            "score": current_window.score, "evidence_level": current_window.evidence_level,
            "dusthana_afflicted": dusthana_afflicted,
        }
    better_window_out = None
    if verdict == "wait_for_better_window" and timing.windows:
        best = timing.windows[0]
        better_window_out = {
            "start_date": best.start_date, "end_date": best.end_date,
            "mahadasha_lord": best.mahadasha_lord, "mahadasha_lord_name": best.mahadasha_lord_name,
            "antardasha_lord": best.antardasha_lord, "antardasha_lord_name": best.antardasha_lord_name,
            "score": best.score,
        }

    prior_rows = []
    if verdict == "neutral":
        result = await db.execute(
            select(PredictionQueryLog)
            .where(PredictionQueryLog.user_id == profile.user_id, PredictionQueryLog.intent == "marriage_decision")
            .order_by(PredictionQueryLog.created_at.desc())
            .limit(2)
        )
        prior_rows = result.scalars().all()
    prior_verdicts = [row.result_summary.get("verdict") for row in prior_rows]
    history_nudge = _history_nudge(verdict, prior_verdicts)
    history_dates = [row.created_at.date().isoformat() for row in prior_rows] if history_nudge is not None else []

    reasoning = decision_reason_text(
        "marriage", verdict, language,
        current_period_lord=current_window.antardasha_lord if current_window else None,
        dusthana_afflicted=dusthana_afflicted,
        better_window_start=better_window_out["start_date"].isoformat() if better_window_out else None,
        history_nudge=history_nudge,
        history_dates=history_dates,
    )

    await log_prediction_query(
        db, profile.user_id, "marriage_decision", None, language,
        {"verdict": verdict, "current_period_start": current_window.start_date.isoformat() if current_window else None},
    )

    return DecisionResponse(
        decision_type="marriage", language=language, verdict=verdict, reasoning=reasoning,
        current_period=current_period_out, better_window=better_window_out, history_nudge=history_nudge,
    )


def _property_evidence_out(e) -> PropertyRuleEvidence:
    return PropertyRuleEvidence(
        rule_id=e.rule_id, type=e.type, description=e.description,
        source=e.source, chapter=e.chapter, verses=e.verses,
    )


_PROPERTY_INTENT_REFRAME = {
    "property_sale": PROPERTY_INTENT_REFRAME_SALE,
    "property_inheritance": PROPERTY_INTENT_REFRAME_INHERITANCE,
    "property_relocation": PROPERTY_INTENT_REFRAME_RELOCATION,
}
# Maps a PropertyIntent to the label key prediction_templates._DECISION_
# LABEL_EN/HI (and decision_reason_text's verdict-headline interpolation)
# already use — "property_purchase" reuses "house_purchase" (Phase 5's own
# label, unchanged) so chat.py's existing house_purchase_decision category
# keeps its exact reasoning text; the 3 new intents get their own labels.
_PROPERTY_INTENT_DECISION_LABEL_KEY = {
    "property_purchase": "house_purchase", "property_sale": "property_sale",
    "property_inheritance": "property_inheritance", "property_relocation": "property_relocation",
}


async def get_property_analysis(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, language: Language,
    intent: PropertyIntent = "property_purchase", direction: Direction = "future",
) -> PropertyAnalysis:
    """"When will I buy my first house?" (Phase 8) and its 3 Phase-9
    siblings — property_sale/property_inheritance/property_relocation reuse
    the IDENTICAL BPHS Ch.48 v.2-4 signal (the 4th-lord's Dasha/Antardasha
    is associated with acquisition of house and land), reinterpreted by
    context rather than computed differently — see app.astro.property_
    analysis for the full classical/derived citation discipline, and its
    PROPERTY_INTENT_REFRAME_* constants for why the citation's own
    description is never silently rewritten to claim something the verse
    didn't say. The other 4 documented-but-unimplemented intents (see
    schemas.property.IMPLEMENTED_PROPERTY_INTENTS) get an honest "not yet
    supported" response, never a guess routed through this logic.

    Reuses the "property" EventType Phase 5 already wired through the
    generic window-scanning engine (get_life_event_timing) — zero new
    scanning code for any of the 4 implemented intents, since they all
    describe the SAME underlying astrological activation. What's genuinely
    new: the natal property_promise assessment (data get_chart already
    computed) and the current/next/medium-term/long-term framing, mirroring
    get_marriage_decision's own "thin wrapper over the real engine"
    precedent — plus, as of Phase 9, the D4 (Chaturthamsha) refinement
    layer (see app.astro.vargas.chaturthamsa_sign_index)."""
    if intent not in IMPLEMENTED_PROPERTY_INTENTS:
        note = (
            f"यह तरह का संपत्ति सवाल अभी समर्थित नहीं है — फ़िलहाल केवल खरीद, बिक्री, विरासत और "
            f"स्थानांतरण को ही यह इंजन कवर करता है।" if language == "hi" else
            f"This kind of property question ({intent.replace('property_', '')}) isn't supported by "
            "this engine yet — only purchase, sale, inheritance, and relocation are currently covered."
        )
        await log_prediction_query(
            db, profile.user_id, "property_analysis", None, language, {"intent": intent, "blocked": True}
        )
        return PropertyAnalysis(intent=intent, language=language, note=note)

    life_state_row = await get_life_state(db, profile.user_id)
    life_state = decrypt_life_state(life_state_row) if life_state_row else None

    d1 = await get_chart(db, profile, birth, "D1")
    fourth_lord = house_lord(4, d1.lagna_sign_index)
    fourth_lord_planet = next(p for p in d1.planets if p.planet == fourth_lord)
    mars_planet = next(p for p in d1.planets if p.planet == "Ma")
    names = PLANET_NAMES_HI if language == "hi" else PLANET_NAMES_EN

    fourth_lord_dignity = fourth_lord_planet.dignity or "neutral"
    fourth_lord_combust = bool(fourth_lord_planet.combust)

    # Phase 9 — D4 refinement layer: only computable when the D1 chart's
    # degree-in-sign is available (absent on old cached rows) — honestly
    # skipped, never guessed, when it isn't.
    d4_factors = None
    fourth_lord_d4_dignity = None
    if fourth_lord_planet.degree_in_sign is not None:
        fourth_lord_longitude = fourth_lord_planet.sign_index * 30 + fourth_lord_planet.degree_in_sign
        fourth_lord_d4_sign = chaturthamsa_sign_index(fourth_lord_longitude)
        fourth_lord_d4_dignity = planet_dignity(fourth_lord, fourth_lord_d4_sign)
        d4_factors = PropertyD4Factors(
            fourth_lord_d4_sign_index=fourth_lord_d4_sign,
            fourth_lord_d4_dignity=fourth_lord_d4_dignity,
            confirmed=fourth_lord_d4_dignity in ("exalted", "own_sign"),
        )

    promise = compute_property_promise(fourth_lord_dignity, fourth_lord_combust, fourth_lord_d4_dignity)

    factors = PropertyFactors(
        fourth_lord=fourth_lord, fourth_lord_name=names[fourth_lord],
        fourth_lord_dignity=fourth_lord_dignity, fourth_lord_combust=fourth_lord_combust,
        planets_in_fourth_house=[p.planet for p in d1.planets if p.house == 4],
        mars_dignity=mars_planet.dignity or "neutral", d4=d4_factors,
    )
    property_promise_out = PropertyPromise(
        status=promise.status, evidence=[_property_evidence_out(e) for e in promise.evidence]
    )

    # Spec §9: already owning property doesn't make a PURCHASE question moot
    # the way "already married" does for marriage_decision — it's a real
    # clarifying-question case (another/investment property?), handled by
    # chat_understanding's gap-check, not a hard block here; SALE is the
    # inverse case (can't sell what's never been indicated as owned).
    # INHERITANCE/RELOCATION carry no such life-state gate.
    note = None
    if intent == "property_purchase" and life_state is not None and life_state.housing_status == "owns_property":
        note = (
            "आपने बताया है कि आपके पास पहले से ही एक संपत्ति है — यह विश्लेषण मान रहा है कि आप किसी "
            "अतिरिक्त या दूसरी संपत्ति के बारे में पूछ रहे हैं।" if language == "hi" else
            "You've indicated you already own property — this reading assumes you're asking about "
            "an additional or investment property, not a first home."
        )
    elif intent == "property_sale" and (life_state is None or life_state.housing_status != "owns_property"):
        note = (
            "आपने प्रोफ़ाइल में संपत्ति के मालिक होने का ज़िक्र नहीं किया है — यह विश्लेषण मान रहा है कि आप "
            "काल्पनिक रूप से पूछ रहे हैं, या यह संपत्ति अभी आपकी प्रोफ़ाइल में दर्ज नहीं है।" if language == "hi" else
            "You haven't indicated owning property in your profile — this reading assumes you're "
            "asking hypothetically, or about a property not yet reflected there."
        )

    timing = await get_life_event_timing(db, profile, birth, "property", language, direction)

    await log_prediction_query(
        db, profile.user_id, "property_analysis", direction, language,
        {"intent": intent, "property_promise_status": promise.status, "window_count": len(timing.windows)},
    )

    if direction == "past":
        return PropertyAnalysis(
            intent=intent, language=language, property_promise=property_promise_out,
            property_factors=factors, historical_windows=timing.windows, note=note,
        )

    # Spec §8: current / next relevant / medium-term / long-term peak — four
    # genuinely distinct, already-computed windows (never a fabricated
    # date), chronologically ordered so "next" really means nearest-future,
    # not just highest-scored. `long_term_peak` is the engine's own
    # existing field, passed through as-is.
    windows_by_date = sorted(timing.windows, key=lambda w: w.start_date)
    today = date.today()
    current_period = next((w for w in windows_by_date if w.start_date <= today <= w.end_date), None)
    remaining = [w for w in windows_by_date if w is not current_period and w.start_date > today]
    next_relevant_window = remaining[0] if remaining else None
    medium_term_window = remaining[1] if len(remaining) > 1 else None

    # Spec §16: astro_strength/event_confidence are the primary window's
    # OWN already-computed score/confidence, relabeled — never a new number.
    primary = current_period or next_relevant_window
    astro_strength = primary.score if primary else None
    event_confidence = primary.confidence if primary else None

    evidence: list[PropertyRuleEvidence] = []
    if primary is not None:
        if primary.evidence_level == "house_lord_antardasha":
            evidence.append(_property_evidence_out(BPHS_48_2_4))
        elif primary.evidence_level == "karaka_antardasha":
            evidence.append(_property_evidence_out(PROPERTY_KARAKA_MARS_SATURN))
        evidence.append(_property_evidence_out(PROPERTY_TIMING_WINDOWS))
        if intent in _PROPERTY_INTENT_REFRAME:
            evidence.append(_property_evidence_out(_PROPERTY_INTENT_REFRAME[intent]))

    return PropertyAnalysis(
        intent=intent, language=language,
        property_promise=property_promise_out, property_factors=factors,
        current_period=current_period, next_relevant_window=next_relevant_window,
        medium_term_window=medium_term_window, long_term_peak=timing.long_term_peak,
        astro_strength=astro_strength, event_confidence=event_confidence,
        evidence=evidence, note=note,
    )


def property_analysis_decision_view(analysis: PropertyAnalysis, language: Language) -> dict:
    """Derives a DecisionResponse-compatible dict (verdict/reasoning/
    current_period/better_window/history_nudge/note) from an ALREADY-
    computed PropertyAnalysis — pure, no DB/engine calls — so chat.py's
    deterministic TemplateInterpreter path (which expects that exact shape,
    same as job_change_decision/business_start_decision) works for all 4
    implemented intents unchanged. See get_property_analysis for how the
    analysis itself is computed."""
    label_key = _PROPERTY_INTENT_DECISION_LABEL_KEY.get(analysis.intent, "house_purchase")
    if analysis.note:
        verdict: Literal["favorable", "unfavorable", "wait_for_better_window", "neutral"] = "neutral"
        reasoning = analysis.note
    else:
        if analysis.current_period is not None and analysis.current_period.evidence_level in (
            "house_lord_antardasha", "karaka_antardasha"
        ):
            verdict = "favorable"
        elif analysis.next_relevant_window is not None:
            verdict = "wait_for_better_window"
        else:
            verdict = "neutral"
        reasoning = decision_reason_text(
            label_key, verdict, language,
            current_period_lord=analysis.current_period.antardasha_lord if analysis.current_period else None,
            dusthana_afflicted=False,
            better_window_start=analysis.next_relevant_window.start_date.isoformat() if analysis.next_relevant_window else None,
            history_nudge=None, history_dates=[],
        )
    return {
        "verdict": verdict,
        "reasoning": reasoning,
        "current_period": analysis.current_period.model_dump(mode="json") if analysis.current_period else None,
        "better_window": analysis.next_relevant_window.model_dump(mode="json") if analysis.next_relevant_window else None,
        "history_nudge": None,
        "note": analysis.note,
    }


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
