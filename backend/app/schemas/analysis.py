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
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("period must not exceed one year")
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
