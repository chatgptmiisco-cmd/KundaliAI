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


class MarriageWindow(BaseModel):
    start_date: date
    end_date: date
    mahadasha_lord: str
    mahadasha_lord_name: str
    antardasha_lord: str
    antardasha_lord_name: str
    score: float
    reason: str
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


class MarriageTimingResponse(BaseModel):
    language: str
    direction: str
    windows: list[MarriageWindow]
    manglik_note: str | None
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


class LifeEventTimingResponse(BaseModel):
    event_type: str
    language: str
    direction: str
    windows: list[LifeEventWindow]
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
