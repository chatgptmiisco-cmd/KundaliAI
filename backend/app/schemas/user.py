from datetime import date

from pydantic import BaseModel, Field


class BirthDataIn(BaseModel):
    name: str
    date_of_birth: date
    time_of_birth: str = Field(pattern=r"^\d{2}:\d{2}$", description="HH:MM, 24-hour, local time")
    time_uncertain: bool = False
    time_uncertainty_minutes: int | None = None
    place_of_birth: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone_offset_hours: float = Field(ge=-12, le=14)


class BirthDataOut(BirthDataIn):
    version: int


class UserProfileOut(BaseModel):
    id: str
    email: str | None
    phone: str | None
    preferred_language: str
    subscription_tier: str
    birth_data: BirthDataOut | None


class UserProfileUpdate(BaseModel):
    preferred_language: str | None = None
    birth_data: BirthDataIn | None = None
