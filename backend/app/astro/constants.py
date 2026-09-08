"""Fixed Vedic astrology reference data: sign/nakshatra/planet names and the
Vimshottari dasha sequence. Every value here is a well-documented classical
constant, not something computed — kept in one place so the calculation
modules stay readable and every magic number is traceable to its name.
"""
from typing import Literal

PlanetKey = Literal["Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Ra", "Ke"]

SIGN_NAMES_EN = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
SIGN_NAMES_HI = [
    "मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या",
    "तुला", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन",
]

# 0 = movable (chara), 1 = fixed (sthira), 2 = dual (dwiswabhava) — indexed by
# sign index 0=Aries..11=Pisces. Used to derive the Navamsa starting sign.
SIGN_MODALITY = [0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2]

# Natural rulership (sign lord), indexed by sign index 0=Aries..11=Pisces —
# used to work out which house a given house-lord occupies, the backbone of
# rule-based (non-LLM) chart reasoning in app.services.interpretation.
SIGN_LORDS: list[PlanetKey] = ["Ma", "Ve", "Me", "Mo", "Su", "Me", "Ve", "Ma", "Ju", "Sa", "Sa", "Ju"]

# Classical exaltation/debilitation signs (Uccha/Neecha) and own signs
# (Swakshetra) for the seven classical planets. Rahu/Ketu are deliberately
# excluded — their exaltation is not settled across classical texts, so
# dignity reasoning here only applies to Su/Mo/Ma/Me/Ju/Ve/Sa.
EXALTATION_SIGN: dict[PlanetKey, int] = {
    "Su": 0, "Mo": 1, "Ma": 9, "Me": 5, "Ju": 3, "Ve": 11, "Sa": 6,
}
DEBILITATION_SIGN: dict[PlanetKey, int] = {
    "Su": 6, "Mo": 7, "Ma": 3, "Me": 11, "Ju": 9, "Ve": 5, "Sa": 0,
}
OWN_SIGNS: dict[PlanetKey, list[int]] = {
    "Su": [4], "Mo": [3], "Ma": [0, 7], "Me": [2, 5], "Ju": [8, 11], "Ve": [1, 6], "Sa": [9, 10],
}

NAKSHATRA_NAMES_EN = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]
NAKSHATRA_NAMES_HI = [
    "अश्विनी", "भरणी", "कृत्तिका", "रोहिणी", "मृगशिरा", "आर्द्रा",
    "पुनर्वसु", "पुष्य", "आश्लेषा", "मघा", "पूर्वा फाल्गुनी", "उत्तरा फाल्गुनी",
    "हस्त", "चित्रा", "स्वाति", "विशाखा", "अनुराधा", "ज्येष्ठा",
    "मूल", "पूर्वाषाढ़ा", "उत्तराषाढ़ा", "श्रवण", "धनिष्ठा", "शतभिषा",
    "पूर्वा भाद्रपद", "उत्तरा भाद्रपद", "रेवती",
]

PLANET_NAMES_EN: dict[PlanetKey, str] = {
    "Su": "Sun", "Mo": "Moon", "Ma": "Mars", "Me": "Mercury", "Ju": "Jupiter",
    "Ve": "Venus", "Sa": "Saturn", "Ra": "Rahu", "Ke": "Ketu",
}
PLANET_NAMES_HI: dict[PlanetKey, str] = {
    "Su": "सूर्य", "Mo": "चंद्र", "Ma": "मंगल", "Me": "बुध", "Ju": "गुरु",
    "Ve": "शुक्र", "Sa": "शनि", "Ra": "राहु", "Ke": "केतु",
}

NAKSHATRA_SPAN_DEG = 360 / 27  # 13°20'

# The Vimshottari cycle: 9 lords in a fixed order, each nakshatra's lord is
# this sequence repeated 3x (27 = 9*3). Years sum to 120 (one full cycle).
VIMSHOTTARI_SEQUENCE: list[PlanetKey] = ["Ke", "Ve", "Su", "Mo", "Ma", "Ra", "Ju", "Sa", "Me"]
VIMSHOTTARI_YEARS: dict[PlanetKey, int] = {
    "Ke": 7, "Ve": 20, "Su": 6, "Mo": 10, "Ma": 7, "Ra": 18, "Ju": 16, "Sa": 19, "Me": 17,
}
VIMSHOTTARI_TOTAL_YEARS = sum(VIMSHOTTARI_YEARS.values())  # 120
assert VIMSHOTTARI_TOTAL_YEARS == 120

DAYS_PER_YEAR = 365.2425  # Gregorian mean year, used for dasha duration math


def nakshatra_lord(nakshatra_index: int) -> PlanetKey:
    """nakshatra_index: 0=Ashwini .. 26=Revati."""
    return VIMSHOTTARI_SEQUENCE[nakshatra_index % 9]
