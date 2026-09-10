from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PeriodAnalysisRequest(BaseModel):
    start_date: date
    end_date: date
    language: Literal["en", "hi"] = "en"
    mode: Literal["simple", "detailed"] = "simple"

    @model_validator(mode="after")
    def check_range(self) -> "PeriodAnalysisRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        # The frontend's only caller of this endpoint (PeriodAnalysisScreen)
        # analyzes a full Mahadasha at a time, not just a short sub-period —
        # and a single Vimshottari Mahadasha can run up to 20 years (Venus).
        # The computation itself has no dependency on a short range (it just
        # picks the range's midpoint for a representative transit snapshot),
        # so the real constraint is "one Vimshottari Mahadasha", not "one
        # year" — a much larger, generous cap that still rejects a request
        # spanning multiple lifetimes' worth of dashas by mistake.
        if (self.end_date - self.start_date).days > 8000:
            raise ValueError("period must not exceed roughly one Mahadasha (~22 years)")
        return self


class PeriodAnalysisResponse(BaseModel):
    start_date: date
    end_date: date
    language: str
    rating: int = Field(ge=1, le=10)
    theme: str
    risks: list[str]
    opportunities: list[str]
    summary: str
    cached: bool
    remaining_free_analyses_this_month: int | None
