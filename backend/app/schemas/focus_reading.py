from datetime import date

from pydantic import BaseModel


class FocusAreaReading(BaseModel):
    area: str  # family | health | career | marriage_relationships | friends
    house: int
    house_lord: str
    house_lord_house: int
    dignity: str  # exalted | debilitated | own_sign | neutral
    rating: int
    theme: str
    summary: str
    meaning: str
    avoid_today: str
    focus_today: str
    transit_note: str | None


class FocusReadingsResponse(BaseModel):
    date: date
    language: str
    readings: list[FocusAreaReading]
    cached: bool
