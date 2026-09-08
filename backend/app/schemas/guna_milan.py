from datetime import date

from pydantic import BaseModel, Field


class GunaMilanRequest(BaseModel):
    partner_name: str
    partner_date_of_birth: date
    partner_time_of_birth: str = Field(pattern=r"^\d{2}:\d{2}$")
    partner_place_of_birth: str
    partner_latitude: float = Field(ge=-90, le=90)
    partner_longitude: float = Field(ge=-180, le=180)
    partner_timezone_offset_hours: float = Field(ge=-12, le=14)
    language: str = "en"


class KootaOut(BaseModel):
    key: str
    label: str
    score: float
    max_score: float
    summary: str


class GunaMilanResponse(BaseModel):
    language: str
    your_moon_sign: str
    your_nakshatra: str
    partner_moon_sign: str
    partner_nakshatra: str
    total_score: float
    max_total: float
    kootas: list[KootaOut]
    mangal_dosha_mismatch: bool
    mangal_dosha_note: str | None
    verdict: str
    verdict_message: str
