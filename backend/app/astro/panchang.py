"""Panchang basics: tithi (lunar day), nakshatra pada (quarter), and the
weekday planetary lord — none of this existed in the engine before. Every
value here is plain arithmetic on Sun/Moon sidereal longitude or the
Gregorian weekday, same "no LLM" style as every other app.astro module.
"""
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.astro.constants import NAKSHATRA_SPAN_DEG, PlanetKey

Paksha = Literal["shukla", "krishna"]
# The 5-fold classical tithi grouping (Nanda/Bhadra/Jaya/Rikta/Purna), each
# repeating every 5 tithis within a paksha — this is what maps to a usable
# "energy tag" for the day, rather than exposing all 30 tithi names.
TithiGroup = Literal["nanda", "bhadra", "jaya", "rikta", "purna"]
TithiEnergyTag = Literal["start", "consolidate", "effort", "avoid_starts", "finish"]

_GROUP_BY_POSITION: dict[int, TithiGroup] = {
    1: "nanda", 2: "bhadra", 3: "jaya", 4: "rikta", 0: "purna",  # 0 covers 5/10/15
}
_ENERGY_TAG_BY_GROUP: dict[TithiGroup, TithiEnergyTag] = {
    "nanda": "start", "bhadra": "consolidate", "jaya": "effort",
    "rikta": "avoid_starts", "purna": "finish",
}


@dataclass(frozen=True)
class Tithi:
    index: int  # 1-30, 1-15 waxing then 1-15 waning
    paksha: Paksha
    number_in_paksha: int  # 1-15
    group: TithiGroup
    energy_tag: TithiEnergyTag


def compute_tithi(sun_longitude: float, moon_longitude: float) -> Tithi:
    """Tithi = 1/30th of the Moon's angular distance ahead of the Sun."""
    diff = (moon_longitude - sun_longitude) % 360
    index = int(diff // 12) + 1  # 1-30
    paksha: Paksha = "shukla" if index <= 15 else "krishna"
    number_in_paksha = index if index <= 15 else index - 15
    group = _GROUP_BY_POSITION[number_in_paksha % 5]
    return Tithi(
        index=index, paksha=paksha, number_in_paksha=number_in_paksha,
        group=group, energy_tag=_ENERGY_TAG_BY_GROUP[group],
    )


# The 15 classical tithi names, shared by both pakshas except the 15th (the
# waxing 15th is Purnima/full moon; the waning 15th is Amavasya/new moon).
_TITHI_NAMES_EN = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi", "Saptami",
    "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi",
]
_TITHI_NAMES_HI = [
    "प्रतिपदा", "द्वितीया", "तृतीया", "चतुर्थी", "पंचमी", "षष्ठी", "सप्तमी",
    "अष्टमी", "नवमी", "दशमी", "एकादशी", "द्वादशी", "त्रयोदशी", "चतुर्दशी",
]


def tithi_name(tithi: Tithi, language: str) -> str:
    if tithi.number_in_paksha == 15:
        if tithi.paksha == "shukla":
            return "पूर्णिमा" if language == "hi" else "Purnima"
        return "अमावस्या" if language == "hi" else "Amavasya"
    names = _TITHI_NAMES_HI if language == "hi" else _TITHI_NAMES_EN
    return names[tithi.number_in_paksha - 1]


# --- Lunar month (amanta convention) ---------------------------------------
# The lunar month takes its name from the sidereal solar sign the Sun
# occupies during most of that month — the standard, widely-used
# approximation for computing the amanta lunar month programmatically.
# Documented simplification (same honesty convention as app.astro.doshas):
# the classically precise rule names the month from the nakshatra of that
# month's full/new moon, which very occasionally (near a month boundary, or
# in an adhik/kshaya leap month) disagrees with this solar-sign shortcut by
# one month. North Indian (purnimanta) sources may also name the *same* days
# one month later than the amanta names used here.
LUNAR_MONTH_NAMES_EN = [
    "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada", "Ashwin",
    "Kartika", "Margashirsha", "Pausha", "Magha", "Phalguna", "Chaitra",
]
LUNAR_MONTH_NAMES_HI = [
    "वैशाख", "ज्येष्ठ", "आषाढ़", "श्रावण", "भाद्रपद", "आश्विन",
    "कार्तिक", "मार्गशीर्ष", "पौष", "माघ", "फाल्गुन", "चैत्र",
]


def lunar_month_index(sun_longitude: float) -> int:
    """0=Vaishakha (Sun in Aries) .. 11=Chaitra (Sun in Pisces)."""
    return int(sun_longitude % 360 // 30)


def lunar_month_name(sun_longitude: float, language: str) -> str:
    names = LUNAR_MONTH_NAMES_HI if language == "hi" else LUNAR_MONTH_NAMES_EN
    return names[lunar_month_index(sun_longitude)]


# --- Festivals --------------------------------------------------------------
# A deliberately small, unambiguous starter set of major festivals keyed by
# (lunar month index, paksha, tithi number-in-paksha) — same "starter
# catalog, not exhaustive" honesty convention as app.astro.doshas. Regional
# variants, purely nakshatra-timed observances, and movable minor festivals
# are out of scope for this pass.
_FESTIVALS: dict[tuple[int, Paksha, int], tuple[str, str]] = {
    (11, "shukla", 1): ("Gudi Padwa / Chaitra Navratri begins", "गुड़ी पड़वा / चैत्र नवरात्रि आरंभ"),
    (11, "shukla", 9): ("Ram Navami", "राम नवमी"),
    (3, "shukla", 15): ("Raksha Bandhan", "रक्षा बंधन"),
    (4, "krishna", 8): ("Krishna Janmashtami", "कृष्ण जन्माष्टमी"),
    (4, "shukla", 4): ("Ganesh Chaturthi", "गणेश चतुर्थी"),
    (5, "shukla", 1): ("Sharad Navratri begins", "शरद नवरात्रि आरंभ"),
    (5, "shukla", 10): ("Dussehra (Vijayadashami)", "दशहरा (विजयादशमी)"),
    (6, "krishna", 15): ("Diwali (Amavasya)", "दिवाली (अमावस्या)"),
    (6, "shukla", 1): ("Govardhan Puja", "गोवर्धन पूजा"),
    (6, "shukla", 2): ("Bhai Dooj", "भाई दूज"),
    (9, "shukla", 5): ("Vasant Panchami", "वसंत पंचमी"),
    (10, "krishna", 14): ("Maha Shivratri", "महाशिवरात्रि"),
    (10, "shukla", 15): ("Holi", "होली"),
}


def festival_today(lunar_month: int, tithi: Tithi, language: str) -> str | None:
    entry = _FESTIVALS.get((lunar_month, tithi.paksha, tithi.number_in_paksha))
    if entry is None:
        return None
    return entry[1] if language == "hi" else entry[0]


def is_makar_sankranti(sun_longitude_today: float, sun_longitude_yesterday: float) -> bool:
    """Makar Sankranti is a solar (not lunar) festival — the day the Sun's
    sidereal longitude crosses into Capricorn (sign index 9, i.e. 270 deg).
    Checked as a sign-index crossing between two consecutive days rather than
    a fixed Gregorian date, since it drifts slightly across the centuries."""
    return int(sun_longitude_yesterday // 30) != 9 and int(sun_longitude_today // 30) == 9


def nakshatra_pada(moon_longitude: float) -> int:
    """1-4: which quarter of its current nakshatra the Moon sits in."""
    degree_in_nakshatra = moon_longitude % NAKSHATRA_SPAN_DEG
    pada_span = NAKSHATRA_SPAN_DEG / 4
    return int(degree_in_nakshatra // pada_span) + 1


# Python's date.weekday(): Monday=0 .. Sunday=6. Classical weekday lordship
# (Sun=Sunday, Moon=Monday, ... Saturn=Saturday) reindexed to that scale.
_WEEKDAY_LORDS: dict[int, PlanetKey] = {
    0: "Mo", 1: "Ma", 2: "Me", 3: "Ju", 4: "Ve", 5: "Sa", 6: "Su",
}

# Classical colour associated with each planet's day — used as "today's
# colour" since it's tied to the weekday lord by long-standing convention.
WEEKDAY_COLOR_EN: dict[PlanetKey, str] = {
    "Su": "Orange/Gold", "Mo": "White", "Ma": "Red", "Me": "Green",
    "Ju": "Yellow", "Ve": "Pastel/White", "Sa": "Blue/Black",
}
WEEKDAY_COLOR_HI: dict[PlanetKey, str] = {
    "Su": "नारंगी/सुनहरा", "Mo": "सफ़ेद", "Ma": "लाल", "Me": "हरा",
    "Ju": "पीला", "Ve": "हल्का/सफ़ेद", "Sa": "नीला/काला",
}


def weekday_lord(for_date: date) -> PlanetKey:
    return _WEEKDAY_LORDS[for_date.weekday()]
