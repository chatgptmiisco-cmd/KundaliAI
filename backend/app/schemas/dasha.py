from datetime import datetime

from pydantic import BaseModel


class AntardashaOut(BaseModel):
    lord: str
    lord_name_en: str
    lord_name_hi: str
    start: datetime
    end: datetime
    is_current: bool


class MahadashaOut(BaseModel):
    lord: str
    lord_name_en: str
    lord_name_hi: str
    start: datetime
    end: datetime
    is_current: bool
    antardashas: list[AntardashaOut]


class DashaTimelineResponse(BaseModel):
    mahadashas: list[MahadashaOut]
    cached: bool


class SubPeriodOut(BaseModel):
    lord: str
    lord_name_en: str
    lord_name_hi: str
    start: datetime
    end: datetime


class CurrentDashaResponse(BaseModel):
    mahadasha: MahadashaOut
    antardasha: AntardashaOut
    pratyantardasha: SubPeriodOut
