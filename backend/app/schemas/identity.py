from pydantic import BaseModel


class SignIdentity(BaseModel):
    sign_en: str
    sign_hi: str
    # What this point classically represents (fixed reference copy — same
    # for anyone with this Lagna/Moon/Sun).
    meaning_en: str
    meaning_hi: str
    # The real, per-chart consequence: where this point actually sits and how
    # well-placed it is, and what that means for THIS user specifically — the
    # primary, led-with fact; `meaning_*` above is the secondary glossary note.
    real_effect_en: str
    real_effect_hi: str


class NakshatraIdentity(BaseModel):
    name_en: str
    name_hi: str
    pada: int
    lord_en: str
    lord_hi: str
    symbol_en: str
    symbol_hi: str
    meaning_en: str
    meaning_hi: str


class ElementModalityPoint(BaseModel):
    point_key: str  # "Lagna" | PlanetKey
    point_label_en: str
    point_label_hi: str
    element_en: str
    element_hi: str
    modality_en: str
    modality_hi: str


class IdentityResponse(BaseModel):
    lagna: SignIdentity
    moon_sign: SignIdentity
    sun_sign: SignIdentity
    nakshatra: NakshatraIdentity
    element_modality: list[ElementModalityPoint]
