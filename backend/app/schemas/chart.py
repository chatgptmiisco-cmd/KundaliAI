from datetime import date

from pydantic import BaseModel, Field


class AdhocChartIn(BaseModel):
    """Product ask: 'let me check someone else's chart without overwriting
    my own profile.' Deliberately minimal — no name/place text, no
    time_uncertain flag — since only what compute_chart actually needs
    (date/time/timezone/lat/long) is required; the caller resolves the
    place name to coordinates client-side (same geocoding already used for
    the user's own birth-data form) before calling this."""
    date_of_birth: date
    time_of_birth: str = Field(pattern=r"^\d{2}:\d{2}$", description="HH:MM, 24-hour, local time")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone_offset_hours: float = Field(ge=-12, le=14)
    chart_type: str = "D1"


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
    # A one-line, jargon-free verdict for this house's life area (favorable /
    # unfavorable / mixed, in plain language, no planet names) — separate
    # from the detailed explanation_en/hi above, which stays planet-by-
    # planet for the dedicated chart-explanation screen. Chat's "what does
    # my chart say about X" answers use this instead of the detailed text.
    verdict_en: str
    verdict_hi: str
    # The classical planet ruling this house's sign, and a real, chart-
    # specific sentence blending what THAT planet rules elsewhere with where
    # it's actually placed (see chart_explanation_service.build_planet_theme_
    # sentences) — this is what makes a topic answer feel specific to this
    # one chart instead of reciting the same dasha-lord description used for
    # every other topic too.
    lord: str
    lord_theme_en: str
    lord_theme_hi: str


class PlanetTheme(BaseModel):
    name_en: str
    name_hi: str
    # Raw structured facts (house numbers, sign names) rather than only
    # pre-written prose — chat's prompt now states these explicitly (e.g.
    # "your 10th house is Taurus, ruled by Venus, which sits in your 4th
    # house, Scorpio") instead of paraphrasing them into a generic "home and
    # family" life-area phrase, per direct feedback that naming the actual
    # houses/signs read as more genuinely personal, not more confusing.
    ruled_houses: list[int]
    placed_house: int
    placed_sign_en: str
    placed_sign_hi: str
    theme_en: str
    theme_hi: str


class YogaFinding(BaseModel):
    key: str
    name_en: str
    name_hi: str
    description_en: str
    description_hi: str
    # Direct "yes, you have this" version for chat's dosha/yoga answers — no
    # classical rule/house-number jargon, unlike description_en/hi above
    # (kept for the dedicated chart-explanation screen).
    chat_summary_en: str
    chat_summary_hi: str


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
    # Uranus/Neptune/Pluto — display-only placements shown on the chart for
    # visual parity with common reference charts. Reuses PlanetPlacement's
    # shape but dignity/combust/nakshatra are always None: those are
    # classical-Jyotish concepts that don't apply to these three (see
    # app.astro.ephemeris's outer-planet docstring). Never appears in
    # house_breakdown/yogas/planet_themes above, and never affects dasha or
    # any interpretation — purely decorative chart placements.
    outer_planets: list[PlanetPlacement] = []
    # Keyed by planet code (e.g. "Ve", "Ra") — same signification-blend
    # sentence as each HouseBreakdown's lord_theme_en/hi, but looked up by
    # planet rather than by house, since a Mahadasha/Antardasha lord isn't
    # necessarily any topic's house-lord (Rahu/Ketu never are).
    planet_themes: dict[str, PlanetTheme] = {}
    cached: bool
