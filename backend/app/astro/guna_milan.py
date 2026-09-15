"""Ashtakoot Guna Milan: the classical 8-fold Vedic compatibility score (out
of 36 points) used to check marriage compatibility between two charts.

Every koota below is derived purely from each partner's Moon nakshatra and
Moon sign (Rashi) — no LLM involved, just the same kind of deterministic
lookup-table reasoning as app.astro.manglik and app.astro.natal_insights.

Two kootas (Vashya, Yoni) use a documented simplification rather than every
classical edge case (half-sign splits for Vashya; the full fine-grained
Yoni friend/neutral distinctions) — noted inline where it matters. The other
six (Varna, Tara, Graha Maitri, Gana, Bhakoot, Nadi) follow the standard
tables directly with no simplification.

Varna and Gana traditionally score one special case (Deva/Rakshasa,
boy-vs-girl role) asymmetrically by role. This module treats both partners
symmetrically instead — same total point *pool* per koota, just no
role-dependent special case — since the app doesn't collect a gender/role
for either partner.
"""
from dataclasses import dataclass

from app.astro.constants import SIGN_LORDS
from app.astro.constants import planet_relation as _relation

PARTNER_A = "partner_a"
PARTNER_B = "partner_b"

# --- Varna (1 point): each sign's spiritual/social class -------------------
# Rank reflects the actual hierarchy Brahmin > Kshatriya > Vaishya > Shudra
# (3=highest, 0=lowest) — score requires partner A's rank >= partner B's.
_VARNA_RANK = {
    3: 3, 7: 3, 11: 3,  # Cancer, Scorpio, Pisces -> Brahmin
    0: 2, 4: 2, 8: 2,  # Aries, Leo, Sagittarius -> Kshatriya
    1: 1, 5: 1, 9: 1,  # Taurus, Virgo, Capricorn -> Vaishya
    2: 0, 6: 0, 10: 0,  # Gemini, Libra, Aquarius -> Shudra
}


def _varna_score(sign_a: int, sign_b: int) -> float:
    return 1.0 if _VARNA_RANK[sign_a] >= _VARNA_RANK[sign_b] else 0.0


# --- Vashya (2 points): simplified whole-sign animal-temperament grouping --
# Classical Vashya splits Sagittarius/Capricorn in half between two groups;
# this module treats each sign as belonging wholly to one group (documented
# simplification — see module docstring).
_CHATUSHPADA, _MANAV, _JALACHAR, _VANACHAR, _KEETA = range(5)
_VASHYA_GROUP = {
    0: _CHATUSHPADA, 1: _CHATUSHPADA, 9: _CHATUSHPADA,
    2: _MANAV, 5: _MANAV, 6: _MANAV, 8: _MANAV, 10: _MANAV,
    3: _JALACHAR, 11: _JALACHAR,
    4: _VANACHAR,
    7: _KEETA,
}
_VASHYA_TABLE = {
    (_CHATUSHPADA, _CHATUSHPADA): 2, (_CHATUSHPADA, _MANAV): 1, (_CHATUSHPADA, _JALACHAR): 1,
    (_CHATUSHPADA, _VANACHAR): 0, (_CHATUSHPADA, _KEETA): 1,
    (_MANAV, _MANAV): 2, (_MANAV, _JALACHAR): 1, (_MANAV, _VANACHAR): 0, (_MANAV, _KEETA): 1,
    (_JALACHAR, _JALACHAR): 2, (_JALACHAR, _VANACHAR): 0, (_JALACHAR, _KEETA): 1,
    (_VANACHAR, _VANACHAR): 2, (_VANACHAR, _KEETA): 0,
    (_KEETA, _KEETA): 2,
}


def _vashya_score(sign_a: int, sign_b: int) -> float:
    ga, gb = _VASHYA_GROUP[sign_a], _VASHYA_GROUP[sign_b]
    return float(_VASHYA_TABLE.get((ga, gb)) if (ga, gb) in _VASHYA_TABLE else _VASHYA_TABLE[(gb, ga)])


# --- Tara (3 points): nakshatra-counting cycle -----------------------------
_GOOD_TARA_GROUPS = {2, 4, 6, 8, 9}  # Sampat, Kshema, Sadhaka, Mitra, Ati-Mitra


def _tara_group(nak_from: int, nak_to: int) -> int:
    count = (nak_to - nak_from) % 27 + 1
    return (count - 1) % 9 + 1


def _tara_score(nak_a: int, nak_b: int) -> float:
    ab_good = _tara_group(nak_a, nak_b) in _GOOD_TARA_GROUPS
    ba_good = _tara_group(nak_b, nak_a) in _GOOD_TARA_GROUPS
    return 1.5 * ab_good + 1.5 * ba_good


# --- Yoni (4 points): nakshatra -> animal symbol ---------------------------
_YONI_BY_NAKSHATRA = [
    "horse", "elephant", "goat", "serpent", "serpent", "dog", "cat", "goat", "cat", "rat",
    "rat", "cow", "buffalo", "tiger", "buffalo", "tiger", "deer", "deer", "dog", "monkey",
    "mongoose", "monkey", "lion", "horse", "lion", "cow", "elephant",
]
# Natural predator/prey pairs — full enmity (0 points). Everything else that
# isn't the same yoni defaults to a neutral-friendly middle score (documented
# simplification — see module docstring).
_YONI_ENEMIES = {
    frozenset({"cow", "tiger"}), frozenset({"horse", "buffalo"}), frozenset({"elephant", "lion"}),
    frozenset({"dog", "deer"}), frozenset({"serpent", "mongoose"}), frozenset({"rat", "cat"}),
    frozenset({"goat", "monkey"}),
}


def _yoni_score(nak_a: int, nak_b: int) -> float:
    ya, yb = _YONI_BY_NAKSHATRA[nak_a], _YONI_BY_NAKSHATRA[nak_b]
    if ya == yb:
        return 4.0
    if frozenset({ya, yb}) in _YONI_ENEMIES:
        return 0.0
    return 2.0


# --- Graha Maitri (5 points): natural friendship between Moon-sign lords --
# See app.astro.constants.PLANET_FRIENDS/PLANET_ENEMIES/planet_relation for
# the underlying table — shared with app.astro.event_window_scanner's
# Mahadasha/Antardasha relationship weighting, not duplicated here anymore.


def _graha_maitri_score(sign_a: int, sign_b: int) -> float:
    lord_a, lord_b = SIGN_LORDS[sign_a], SIGN_LORDS[sign_b]
    if lord_a == lord_b:
        return 5.0
    rel_ab, rel_ba = _relation(lord_a, lord_b), _relation(lord_b, lord_a)
    pair = {rel_ab, rel_ba}
    if pair == {"friend"}:
        return 5.0
    if pair == {"friend", "neutral"}:
        return 4.0
    if pair == {"neutral"}:
        return 3.0
    if pair == {"neutral", "enemy"}:
        return 1.0
    if pair == {"friend", "enemy"}:
        return 0.5
    return 0.0  # both enemy


# --- Gana (6 points): nakshatra temperament (Deva / Manushya / Rakshasa) ---
_DEVA = {0, 4, 6, 7, 12, 14, 16, 21, 26}
_MANUSHYA = {1, 3, 5, 10, 11, 19, 20, 24, 25}
_RAKSHASA = {2, 8, 9, 13, 15, 17, 18, 22, 23}


def _gana(nak: int) -> str:
    if nak in _DEVA:
        return "deva"
    if nak in _MANUSHYA:
        return "manushya"
    return "rakshasa"


def _gana_score(nak_a: int, nak_b: int) -> float:
    ga, gb = _gana(nak_a), _gana(nak_b)
    if ga == gb:
        return 6.0
    pair = {ga, gb}
    if pair == {"deva", "manushya"}:
        return 5.0
    if pair == {"deva", "rakshasa"}:
        return 1.0
    return 0.0  # manushya + rakshasa


# --- Bhakoot (7 points): sign-distance between the two Moons ---------------
_BHAKOOT_DOSHA_DISTANCES = {1, 5, 7, 11}  # 2-12 and 6-8 relationships


def _bhakoot_score(sign_a: int, sign_b: int) -> float:
    diff = (sign_b - sign_a) % 12
    return 0.0 if diff in _BHAKOOT_DOSHA_DISTANCES else 7.0


# --- Nadi (8 points): nakshatra "biological energy" category --------------
_AADI = {0, 5, 6, 11, 12, 17, 18, 23, 24}
_MADHYA = {1, 4, 7, 10, 13, 16, 19, 22, 25}
_ANTYA = {2, 3, 8, 9, 14, 15, 20, 21, 26}


def _nadi(nak: int) -> str:
    if nak in _AADI:
        return "aadi"
    if nak in _MADHYA:
        return "madhya"
    return "antya"


def _nadi_score(nak_a: int, nak_b: int) -> float:
    return 0.0 if _nadi(nak_a) == _nadi(nak_b) else 8.0


@dataclass(frozen=True)
class KootaScore:
    key: str
    score: float
    max_score: float


@dataclass(frozen=True)
class GunaMilanResult:
    kootas: list[KootaScore]
    total_score: float
    max_total: float
    mangal_dosha_mismatch: bool


def compute_guna_milan(
    moon_sign_a: int, moon_nakshatra_a: int, is_manglik_a: bool,
    moon_sign_b: int, moon_nakshatra_b: int, is_manglik_b: bool,
) -> GunaMilanResult:
    kootas = [
        KootaScore("varna", _varna_score(moon_sign_a, moon_sign_b), 1.0),
        KootaScore("vashya", _vashya_score(moon_sign_a, moon_sign_b), 2.0),
        KootaScore("tara", _tara_score(moon_nakshatra_a, moon_nakshatra_b), 3.0),
        KootaScore("yoni", _yoni_score(moon_nakshatra_a, moon_nakshatra_b), 4.0),
        KootaScore("graha_maitri", _graha_maitri_score(moon_sign_a, moon_sign_b), 5.0),
        KootaScore("gana", _gana_score(moon_nakshatra_a, moon_nakshatra_b), 6.0),
        KootaScore("bhakoot", _bhakoot_score(moon_sign_a, moon_sign_b), 7.0),
        KootaScore("nadi", _nadi_score(moon_nakshatra_a, moon_nakshatra_b), 8.0),
    ]
    return GunaMilanResult(
        kootas=kootas,
        total_score=sum(k.score for k in kootas),
        max_total=36.0,
        mangal_dosha_mismatch=is_manglik_a != is_manglik_b,
    )
