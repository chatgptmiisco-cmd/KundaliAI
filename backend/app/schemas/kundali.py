from pydantic import BaseModel

from app.schemas.manglik import ManglikStatusResponse


class KeyValueItem(BaseModel):
    label: str
    value: str


class KundaliSection(BaseModel):
    id: str
    title: str
    summary: str
    key_points: list[str]


class KundaliSummary(BaseModel):
    lagna: str
    moon_sign: str
    core_strength: str
    core_challenge: str
    is_manglik: bool
    manglik_one_liner: str


class CompleteKundaliResponse(BaseModel):
    language: str
    basic_details: list[KeyValueItem]
    sections: list[KundaliSection]
    manglik: ManglikStatusResponse
    brutal_truth: str
    summary: KundaliSummary
    cached: bool
