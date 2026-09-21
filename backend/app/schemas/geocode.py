from pydantic import BaseModel


class GeocodeResult(BaseModel):
    display_name: str
    latitude: float
    longitude: float
    # Best-effort estimate (see geocoding_service._estimate_timezone_offset_
    # hours) — a known single-timezone country's fixed offset when the
    # country is recognized, otherwise a longitude/15 approximation. Real
    # historical DST rules aren't modeled.
    timezone_offset_hours: float
