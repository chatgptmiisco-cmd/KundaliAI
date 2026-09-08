from datetime import date

from pydantic import BaseModel


class DailyHoroscopeResponse(BaseModel):
    date: date
    language: str
    tone: str
    focus_areas: list[str]
    tip: str
    summary_text: str
    cached: bool
