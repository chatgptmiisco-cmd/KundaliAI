from pydantic import BaseModel


class PlanetPlacement(BaseModel):
    planet: str
    planet_name_en: str
    planet_name_hi: str
    sign_index: int
    sign_name_en: str
    sign_name_hi: str
    house: int
    retrograde: bool
    # "Grah Spashta" precision fields — the real sidereal degree within the
    # sign (D1 only; None on D9/D10 since a divisional sign has no
    # independent degree of its own), plus the Moon-longitude-derived
    # nakshatra/pada, which every classical software prints alongside sign.
    degree_in_sign: float | None = None
    degree_display: str | None = None  # e.g. "12°32'"
    nakshatra_name_en: str | None = None
    nakshatra_name_hi: str | None = None
    nakshatra_pada: int | None = None
    dignity: str | None = None  # exalted | debilitated | own_sign | neutral (7 classical planets only)
    # True when within classical combustion orb of the Sun — always False for
    # the Sun itself and for Rahu/Ketu (no combustion orb applies to them),
    # null only when longitude is unavailable (pre-existing cached rows).
    # A real-longitude fact, same convention as nakshatra/pada above:
    # unaffected by which divisional chart is shown.
    combust: bool | None = None


class HouseBreakdown(BaseModel):
    house: int
    sign_name_en: str
    sign_name_hi: str
    planets: list[str]
    explanation_en: str
    explanation_hi: str


class YogaFinding(BaseModel):
    key: str
    name_en: str
    name_hi: str
    description_en: str
    description_hi: str


class ChartResponse(BaseModel):
    chart_type: str
    lagna_sign_index: int
    lagna_sign_name_en: str
    lagna_sign_name_hi: str
    lagna_degree_in_sign: float | None = None
    lagna_degree_display: str | None = None
    planets: list[PlanetPlacement]
    summary_en: str
    summary_hi: str
    key_points_en: list[str]
    key_points_hi: list[str]
    house_breakdown: list[HouseBreakdown] = []
    yogas: list[YogaFinding] = []
    cached: bool
