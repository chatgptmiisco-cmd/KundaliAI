from datetime import date

from pydantic import BaseModel


class DoshaSummaryItem(BaseModel):
    key: str
    label: str
    is_present: bool


class DailyReadingResponse(BaseModel):
    date: date
    language: str

    rating: int
    rating_reason: str
    dominant_theme: str
    energy_mode: str
    key_risk: str
    key_opportunity: str
    brutal_truth: str

    mahadasha_label: str
    period_rating: int
    period_type: str
    dominant_life_area: str

    core_strength: str
    core_weakness: str
    stress_pattern: str
    decision_style: str

    moon_nakshatra: str
    moon_mood_tag: str
    transit_highlight: str

    before_you_leave_home: list[str]
    life_growth_task: str
    tithi_tag: str
    tithi_name: str
    paksha: str
    lunar_month: str
    festival: str | None
    today_color: str

    doshas: list[DoshaSummaryItem]
    jupiter_transiting_moon_sign: bool
    lucky_number: int
    today_guidance: list[str]

    cached: bool
