from pydantic import BaseModel


class ManglikStatusResponse(BaseModel):
    is_manglik: bool
    summary: str
    mars_house_from_lagna: int
    mars_house_from_moon: int
    details: list[str]
    cancellations: list[str]
    relationship_note: str
    cached: bool
