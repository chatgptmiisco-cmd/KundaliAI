from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class QuarterOutlook(BaseModel):
    start_date: date
    end_date: date
    dominant_dasha_lord: str
    dominant_dasha_lord_name: str
    theme: str
    rating: int = Field(ge=1, le=10)
    opportunities: list[str]
    risks: list[str]


class YearOutlookResponse(BaseModel):
    year: int
    language: str
    overall_rating: int = Field(ge=1, le=10)
    overall_theme: str
    varsheshwar: str
    varsheshwar_name: str
    muntha_house: int
    quarters: list[QuarterOutlook]
    cached: bool


class MultiYearOutlookResponse(BaseModel):
    years: list[YearOutlookResponse]


class PeakWindow(BaseModel):
    """A narrower sub-range INSIDE a window's own [start_date, end_date) —
    from re-scoring that Antardasha's Pratyantardashas (see
    app.astro.dasha.compute_pratyantardashas) against the same house-lord/
    karaka rule already used at the Antardasha level, restricted to where a
    real Pratyantardasha match narrows the range. Only present when it's a
    genuine narrowing (not the whole window), so e.g. "Peak commitment
    window: Sep-Dec 2024" can sit inside a much wider "Relationship
    activation: Oct 2023-Jun 2026" window. See
    app.services.prediction_service._peak_window_for."""

    start_date: date
    end_date: date


class LongTermPeak(BaseModel):
    """The single highest-scoring plausible-age window in the WHOLE future
    search horizon, regardless of recency — what `windows[0]` would have
    been before v17's earliest-wins-ties-within-a-bucket change (see
    prediction_service._TIMING_ALGO_VERSION's v17/v18 changelog). Only
    populated when it's a genuinely different window from `windows[0]` and
    scores meaningfully higher — a boring chart with nothing better later
    gets `None` here, not a redundant restating of `windows[0]`. Only
    computed for direction="future" — see
    app.services.prediction_service._find_long_term_peak."""

    start_date: date
    end_date: date
    mahadasha_lord: str
    mahadasha_lord_name: str
    antardasha_lord: str
    antardasha_lord_name: str
    score: float


class MarriageWindow(BaseModel):
    start_date: date
    end_date: date
    mahadasha_lord: str
    mahadasha_lord_name: str
    antardasha_lord: str
    antardasha_lord_name: str
    score: float
    reason: str
    peak_window: PeakWindow | None = None
    transit_corroborated: bool
    # Ashtakavarga-derived strength of the corroborating transit (1.0 when
    # not corroborated or when natal Ashtakavarga couldn't be computed) and
    # whether a DIFFERENT malefic obstructs the same house at the same time
    # — see app.astro.transit_corroboration.
    transit_corroboration_strength: float
    transit_obstructed: bool
    # What fraction (0-1) of the sampled points show the obstruction — see
    # app.astro.transit_corroboration.TransitCheck.obstruction_fraction.
    transit_obstruction_fraction: float
    # A real-world sanity factor (NOT classical astrology — see
    # app.astro.life_stage_plausibility), already folded into `score`: 1.0
    # in the typical age range for this event, well below 1.0 for a window
    # landing in infancy or deep old age.
    age_plausibility_multiplier: float
    # False when no astrologically plausible-age window existed anywhere in
    # the search horizon and this is the best available signal anyway — the
    # `reason` text then reinterprets what kind of activation this window
    # plausibly represents instead of stating the literal event (e.g. a
    # childbirth at 63, personal wealth at 14) as the answer. See
    # app.astro.life_stage_plausibility.is_hard_implausible_age.
    literal_event_plausible: bool
    # How directly THIS window's own Antardasha ties to the event:
    # "house_lord_antardasha" (the actual house lord's own Antardasha —
    # classically the strongest signal), "karaka_antardasha" (a real but
    # more generic significator's own Antardasha), or "backdrop_only" (only
    # the broader Mahadasha ties to the event — a much weaker signal). See
    # app.services.prediction_service._evidence_level.
    evidence_level: Literal["house_lord_antardasha", "karaka_antardasha", "backdrop_only"]
    # Plain-language confidence derived 1:1 from evidence_level ("strong" /
    # "moderate" / "low") — lets a consumer (chat, frontend) decide how to
    # present a window without re-deriving the evidence/reason-key logic
    # itself. See app.services.prediction_service._CONFIDENCE_FOR_EVIDENCE.
    confidence: Literal["strong", "moderate", "low"]
    # Phase 2: relabels evidence_level/transit_corroborated/transit_obstructed
    # into a plain marriage-specific stage instead of one generic score — no
    # new astrology, just a clearer name for what the engine already
    # computed. See app.services.prediction_service.get_marriage_timing.
    stage: Literal["marriage", "serious_commitment", "relationship_stress"]
    # Whether this window's own Antardasha lord is exalted or in its own
    # sign in the D9 (Navamsa) chart — the classical marriage-confirmation
    # chart, checked independently of the D1 dasha math this window was
    # already selected from. See app.services.prediction_service's D9
    # lookup in get_marriage_timing.
    d9_confirmed: bool


class MarriageTimingResponse(BaseModel):
    language: str
    direction: str
    windows: list[MarriageWindow]
    manglik_note: str | None
    long_term_peak: LongTermPeak | None = None
    cached: bool


class LifeEventWindow(BaseModel):
    start_date: date
    end_date: date
    mahadasha_lord: str
    mahadasha_lord_name: str
    antardasha_lord: str
    antardasha_lord_name: str
    score: float
    reason: str
    peak_window: PeakWindow | None = None
    transit_corroborated: bool
    transit_corroboration_strength: float
    transit_obstructed: bool
    transit_obstruction_fraction: float
    age_plausibility_multiplier: float
    # See MarriageWindow.literal_event_plausible, .evidence_level, and
    # .confidence above.
    literal_event_plausible: bool
    evidence_level: Literal["house_lord_antardasha", "karaka_antardasha", "backdrop_only"]
    confidence: Literal["strong", "moderate", "low"]
    # Phase 2, event_type="career" only (always None otherwise): relabels
    # the EXISTING house-lord-vs-karaka distinction — Saturn (the house
    # lord) running its own Antardasha reads as "structural_change";  Sun
    # (career's karaka for "authority and status", already in the reason
    # text) reads as "leadership_authority". No new astrology, just a name
    # for a real distinction the engine already computes. See
    # app.services.prediction_service.get_life_event_timing.
    theme: Literal["structural_change", "leadership_authority"] | None = None


class LifeEventTimingResponse(BaseModel):
    event_type: str
    language: str
    direction: str
    windows: list[LifeEventWindow]
    long_term_peak: LongTermPeak | None = None
    # Phase 2: set (with `windows` empty) when event_type="business_partnership"
    # was requested but the user's LifeState doesn't say they're running or
    # considering a business — a generic 7th-house reading would otherwise
    # be indistinguishable from marriage_timing. See
    # app.services.prediction_service.get_life_event_timing.
    note: str | None = None
    cached: bool


class LifeThemeResponse(BaseModel):
    target_date: date
    language: str
    mahadasha_lord: str
    mahadasha_lord_name: str
    antardasha_lord: str
    antardasha_lord_name: str
    sade_sati_active: bool
    dhaiya_active: bool
    rating: int = Field(ge=1, le=10)
    theme: str
    cached: bool


class CurrentPeriod(BaseModel):
    """The Antardasha window covering "now" — what the decision verdict is
    actually evaluating. See app.services.prediction_service._current_period_score."""

    start_date: date
    end_date: date
    mahadasha_lord: str
    mahadasha_lord_name: str
    antardasha_lord: str
    antardasha_lord_name: str
    score: float
    evidence_level: Literal["house_lord_antardasha", "karaka_antardasha", "backdrop_only"]
    # True when the CURRENTLY running Antardasha's own lord is the 6th,
    # 8th, or 12th lord from lagna (dusthana/difficulty houses) — the
    # classical "expect friction or disruption" signal, independent of
    # which specific decision is being asked about. See
    # app.services.prediction_service._is_currently_dusthana_afflicted.
    dusthana_afflicted: bool


class BetterWindow(BaseModel):
    """A meaningfully stronger near-term (within a few years) alternative
    window than the current period — same shape/intent as LongTermPeak,
    just always near-term here since a decision about "now" isn't useful
    if the cited alternative is decades away."""

    start_date: date
    end_date: date
    mahadasha_lord: str
    mahadasha_lord_name: str
    antardasha_lord: str
    antardasha_lord_name: str
    score: float


class DecisionResponse(BaseModel):
    """Answers "should I do X now?" with a verdict, not a list of windows —
    see app.services.prediction_service.get_decision."""

    decision_type: Literal["job_change", "business_start", "house_purchase", "marriage"]
    language: str
    verdict: Literal["favorable", "unfavorable", "wait_for_better_window", "neutral"]
    reasoning: str
    current_period: CurrentPeriod | None = None
    better_window: BetterWindow | None = None
    # Set when a "neutral" verdict was nudged toward favorable/unfavorable
    # by 2 consistent prior PredictionQueryLog entries for this same
    # decision_type — see get_decision's history-nudge logic. A non-neutral
    # verdict is never touched by history, so this is always None then.
    history_nudge: Literal["favorable", "unfavorable"] | None = None
    # Set (with everything else None) when decision_type="business_start"
    # was requested but the user's LifeState doesn't say they're running or
    # considering a business — same gating convention as Phase 2's
    # business_partnership event_type.
    note: str | None = None
