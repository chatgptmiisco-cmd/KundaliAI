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
MODALITY_NAMES_EN = ["Movable", "Fixed", "Dual"]
MODALITY_NAMES_HI = ["चर", "स्थिर", "द्विस्वभाव"]

# 0 = fire, 1 = earth, 2 = air, 3 = water — indexed by sign index 0=Aries..
# 11=Pisces. The classical element cycle repeats every 4 signs starting at
# Aries=fire, so this is `sign_index % 4`, kept as an explicit table (rather
# than computed inline everywhere) for the same readability reason as
# SIGN_MODALITY above.
SIGN_ELEMENT = [0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3]
ELEMENT_NAMES_EN = ["Fire", "Earth", "Air", "Water"]
ELEMENT_NAMES_HI = ["अग्नि", "पृथ्वी", "वायु", "जल"]

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

# Classical Vedic/Chaldean numerology number per planet (1-9, Rahu/Ketu take
# the traditional 4/7 substitutes) — standard reference table, same category
# as the name tables above. Used for "today's number" (the weekday lord's
# number), not a per-user claim.
PLANET_NUMBER: dict[PlanetKey, int] = {
    "Su": 1, "Mo": 2, "Ju": 3, "Ra": 4, "Me": 5, "Ve": 6, "Ke": 7, "Sa": 8, "Ma": 9,
}

# Classical symbol and core theme per nakshatra (standard Jyotish reference
# facts, same category as NAKSHATRA_NAMES_EN/HI above — not a per-user claim).
# Index 0=Ashwini .. 26=Revati, matching NAKSHATRA_NAMES_EN/HI order.
NAKSHATRA_SYMBOL_EN = [
    "Horse's head", "Yoni (womb)", "Razor", "Chariot", "Deer's head", "Teardrop/gem",
    "Bow and quiver", "Cow's udder", "Coiled serpent", "Royal throne", "Front legs of a bed",
    "Back legs of a bed", "Hand", "Bright jewel", "Young shoot swaying in wind", "Triumphal arch",
    "Lotus", "Circular earring", "Bunch of tied roots", "Elephant tusk (front)", "Elephant tusk (rear)",
    "Ear", "Drum", "Empty circle", "Front legs of a funeral cot", "Back legs of a funeral cot", "Fish",
]
NAKSHATRA_SYMBOL_HI = [
    "घोड़े का सिर", "योनि", "उस्तरा", "रथ", "हिरण का सिर", "आंसू/रत्न",
    "धनुष और तरकश", "गाय का थन", "कुंडलित सर्प", "राजसिंहासन", "पलंग के अगले पैर",
    "पलंग के पिछले पैर", "हाथ", "चमकीला रत्न", "हवा में हिलती नई कोंपल", "विजय द्वार",
    "कमल", "गोलाकार बाली", "जड़ों का बंधा गुच्छा", "हाथी का दांत (अगला भाग)", "हाथी का दांत (पिछला भाग)",
    "कान", "ढोल", "खाली वृत्त", "शवयान के अगले पैर", "शवयान के पिछले पैर", "मछली",
]
NAKSHATRA_MEANING_EN = [
    "Speed, healing, and new beginnings.",
    "Restraint, transformation, and the strength to bear burdens.",
    "Sharp focus and the courage to cut through what doesn't serve you.",
    "Growth, beauty, and material abundance.",
    "A searching, curious mind always chasing the next discovery.",
    "Storms that clear the way for renewal.",
    "Renewal, and the return of what was once lost.",
    "Nourishment, care, and steady support for others.",
    "Penetrating insight and a magnetic pull.",
    "Ancestral pride, authority, and legacy.",
    "Rest, pleasure, and creative enjoyment.",
    "Generosity, partnership, and steady goodwill.",
    "Skillful hands and practical resourcefulness.",
    "A gift for design, brilliance, and standing out.",
    "Independence and the flexibility to move with change.",
    "Determined ambition focused on a clear goal.",
    "Devotion, friendship, and cooperative success.",
    "Protective leadership and quiet authority.",
    "Getting to the root of things, even if it means uprooting first.",
    "Early confidence and persuasive strength.",
    "Lasting victory earned through discipline.",
    "Listening, learning, and connecting through communication.",
    "Rhythm, prosperity, and a drive for recognition.",
    "Healing, and an independent, unconventional streak.",
    "Intense transformation through fire and passion.",
    "Deep wisdom and quiet, steady inner strength.",
    "Compassion, guidance, and a gentle journey's end.",
]
NAKSHATRA_MEANING_HI = [
    "गति, उपचार और नई शुरुआत।",
    "संयम, रूपांतरण और बोझ उठाने की शक्ति।",
    "तीव्र एकाग्रता और जो काम न आए उसे काटने का साहस।",
    "वृद्धि, सुंदरता और भौतिक समृद्धि।",
    "खोजी और जिज्ञासु मन, हमेशा नई खोज के पीछे।",
    "तूफ़ान जो नवीनीकरण का रास्ता साफ़ करते हैं।",
    "नवीनीकरण, और जो खो गया था उसकी वापसी।",
    "पोषण, देखभाल और दूसरों को स्थिर सहारा।",
    "गहरी अंतर्दृष्टि और एक चुंबकीय खिंचाव।",
    "पारिवारिक गौरव, अधिकार और विरासत।",
    "आराम, आनंद और रचनात्मक सुख।",
    "उदारता, साझेदारी और स्थिर सद्भावना।",
    "कुशल हाथ और व्यावहारिक साधन-संपन्नता।",
    "डिज़ाइन की प्रतिभा, चमक और अलग दिखने की क्षमता।",
    "स्वतंत्रता और बदलाव के साथ ढलने का लचीलापन।",
    "स्पष्ट लक्ष्य पर केंद्रित दृढ़ महत्वाकांक्षा।",
    "समर्पण, मित्रता और सहयोगी सफलता।",
    "सुरक्षात्मक नेतृत्व और शांत अधिकार।",
    "चीज़ों की जड़ तक पहुंचना, भले ही पहले उखाड़ना पड़े।",
    "शुरुआती आत्मविश्वास और प्रेरक शक्ति।",
    "अनुशासन से अर्जित स्थायी विजय।",
    "सुनना, सीखना और संवाद से जुड़ना।",
    "लय, समृद्धि और पहचान पाने की चाह।",
    "उपचार, और एक स्वतंत्र, अपरंपरागत प्रवृत्ति।",
    "आग और जुनून से गुज़रता गहरा रूपांतरण।",
    "गहरी बुद्धि और शांत, स्थिर आंतरिक शक्ति।",
    "करुणा, मार्गदर्शन और यात्रा का सौम्य समापन।",
]

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
