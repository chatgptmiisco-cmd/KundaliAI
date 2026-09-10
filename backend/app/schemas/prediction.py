from datetime import date

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


class MarriageTimingResponse(BaseModel):
    language: str
    windows: list[MarriageWindow]
    manglik_note: str | None
    cached: bool
