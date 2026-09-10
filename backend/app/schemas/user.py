from datetime import date

from pydantic import BaseModel, Field, field_validator

# Must match the frontend's PreferenceKey union (src/types/kundali.ts) — the
# five Home focus areas a user can follow. Kept as an explicit allow-list
# (not a free-form string) so a stale/renamed key from an old client build
# can never get silently persisted server-side.
VALID_PREFERENCE_KEYS = {"family", "health", "career", "marriageRelationships", "friends"}


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
    preferences: list[str]


class UserProfileUpdate(BaseModel):
    preferred_language: str | None = None
    birth_data: BirthDataIn | None = None


class PreferencesIn(BaseModel):
    preferences: list[str]

    @field_validator("preferences")
    @classmethod
    def check_valid_keys(cls, v: list[str]) -> list[str]:
        invalid = [p for p in v if p not in VALID_PREFERENCE_KEYS]
        if invalid:
            raise ValueError(f"invalid preference keys: {invalid}")
        return v
