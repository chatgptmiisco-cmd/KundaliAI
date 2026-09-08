"""Guna Milan (Ashtakoot marriage-compatibility) orchestration: computes the
user's own D1 chart (cached, as usual) and an ephemeral D1 chart for the
partner's birth details (never persisted or cached — this is a one-off
comparison, not a stored profile), then hands both Moons + Mars placements to
the deterministic app.astro.guna_milan engine.

All of the koota labels/summaries and the overall verdict below are plain,
score-driven text — no LLM call, since the scoring itself is exact classical
arithmetic, not something an interpretation layer needs to generate.
"""
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.astro.charts import compute_chart
from app.astro.constants import NAKSHATRA_NAMES_EN, NAKSHATRA_NAMES_HI, NAKSHATRA_SPAN_DEG, SIGN_NAMES_EN, SIGN_NAMES_HI
from app.astro.ephemeris import julian_day_ut, planet_position
from app.astro.guna_milan import GunaMilanResult, compute_guna_milan
from app.astro.manglik import compute_manglik_facts
from app.db.models.birth_profile import BirthProfile
from app.schemas.guna_milan import GunaMilanRequest, GunaMilanResponse, KootaOut
from app.schemas.user import BirthDataOut
from app.services.chart_service import birth_datetime_utc, get_chart

_KOOTA_LABELS_EN = {
    "varna": "Varna (spiritual compatibility)",
    "vashya": "Vashya (mutual influence)",
    "tara": "Tara (well-being of each partner)",
    "yoni": "Yoni (physical/sexual compatibility)",
    "graha_maitri": "Graha Maitri (mental compatibility)",
    "gana": "Gana (temperament compatibility)",
    "bhakoot": "Bhakoot (family/financial harmony)",
    "nadi": "Nadi (health & genetic compatibility)",
}
_KOOTA_LABELS_HI = {
    "varna": "वर्ण (आध्यात्मिक अनुकूलता)",
    "vashya": "वश्य (आपसी प्रभाव)",
    "tara": "तारा (दोनों की भलाई)",
    "yoni": "योनि (शारीरिक अनुकूलता)",
    "graha_maitri": "ग्रह मैत्री (मानसिक अनुकूलता)",
    "gana": "गण (स्वभाव अनुकूलता)",
    "bhakoot": "भकूट (पारिवारिक व आर्थिक सामंजस्य)",
    "nadi": "नाड़ी (स्वास्थ्य व आनुवंशिक अनुकूलता)",
}


def _koota_summary(key: str, score: float, max_score: float, language: str) -> str:
    ratio = score / max_score if max_score else 0
    if language == "hi":
        if ratio >= 0.75:
            return "बहुत अच्छा मेल।"
        if ratio > 0:
            return "आंशिक मेल।"
        return "मेल नहीं — इस पहलू पर ध्यान दें।"
    if ratio >= 0.75:
        return "Strong match."
    if ratio > 0:
        return "Partial match."
    return "No match — worth paying attention to."


def _build_koota_list(result: GunaMilanResult, language: str) -> list[KootaOut]:
    labels = _KOOTA_LABELS_HI if language == "hi" else _KOOTA_LABELS_EN
    return [
        KootaOut(
            key=k.key, label=labels[k.key], score=k.score, max_score=k.max_score,
            summary=_koota_summary(k.key, k.score, k.max_score, language),
        )
        for k in result.kootas
    ]


def _verdict(total: float, language: str) -> tuple[str, str]:
    if total >= 28:
        band = "excellent"
    elif total >= 21:
        band = "good"
    elif total >= 18:
        band = "average"
    else:
        band = "not_recommended"

    if language == "hi":
        messages = {
            "excellent": "उत्कृष्ट मेल — यह जोड़ा अष्टकूट के अनुसार बहुत अनुकूल है।",
            "good": "अच्छा मेल — ज़्यादातर पहलू सकारात्मक हैं।",
            "average": "औसत मेल — पारंपरिक रूप से स्वीकार्य माना जाता है (न्यूनतम 18 अंक), पर कमज़ोर पहलुओं पर ध्यान दें।",
            "not_recommended": "18 अंक से कम — परंपरागत रूप से इसे आगे बढ़ाने से पहले किसी योग्य ज्योतिषी से सलाह लेने की सलाह दी जाती है।",
        }
    else:
        messages = {
            "excellent": "Excellent match — this pairing scores very favourably under Ashtakoot.",
            "good": "Good match — most aspects come out positive.",
            "average": "Average match — traditionally considered workable (18 is the usual minimum), but the weaker kootas are worth understanding.",
            "not_recommended": "Below 18 — traditionally this score is a signal to consult a qualified astrologer before proceeding.",
        }
    return band, messages[band]


async def get_guna_milan(
    db: AsyncSession, profile: BirthProfile, birth: BirthDataOut, request: GunaMilanRequest
) -> GunaMilanResponse:
    language = request.language

    d1_self = await get_chart(db, profile, birth, "D1")
    moon_self = next(p for p in d1_self.planets if p.planet == "Mo")
    mars_self = next(p for p in d1_self.planets if p.planet == "Ma")

    partner_birth = BirthDataOut(
        name=request.partner_name,
        date_of_birth=request.partner_date_of_birth,
        time_of_birth=request.partner_time_of_birth,
        time_uncertain=False,
        place_of_birth=request.partner_place_of_birth,
        latitude=request.partner_latitude,
        longitude=request.partner_longitude,
        timezone_offset_hours=request.partner_timezone_offset_hours,
        version=0,
    )
    jd_ut_partner = julian_day_ut(birth_datetime_utc(partner_birth))
    d1_partner = compute_chart(jd_ut_partner, partner_birth.latitude, partner_birth.longitude, "D1")
    partner_mars_house = d1_partner.planet_house["Ma"]
    partner_moon_sign = d1_partner.planet_sign_index["Mo"]

    moon_longitude_self = planet_position(julian_day_ut(birth_datetime_utc(birth)), "Mo").longitude
    nakshatra_self = int((moon_longitude_self % 360) // NAKSHATRA_SPAN_DEG)

    moon_longitude_partner = planet_position(jd_ut_partner, "Mo").longitude
    nakshatra_partner = int((moon_longitude_partner % 360) // NAKSHATRA_SPAN_DEG)

    manglik_self = compute_manglik_facts(
        mars_sign_index=next(p.sign_index for p in d1_self.planets if p.planet == "Ma"),
        mars_house_from_lagna=mars_self.house,
        moon_sign_index=moon_self.sign_index,
    )
    manglik_partner = compute_manglik_facts(
        mars_sign_index=d1_partner.planet_sign_index["Ma"],
        mars_house_from_lagna=partner_mars_house,
        moon_sign_index=partner_moon_sign,
    )

    result = compute_guna_milan(
        moon_sign_a=moon_self.sign_index, moon_nakshatra_a=nakshatra_self, is_manglik_a=manglik_self.is_manglik,
        moon_sign_b=partner_moon_sign, moon_nakshatra_b=nakshatra_partner, is_manglik_b=manglik_partner.is_manglik,
    )

    band, verdict_message = _verdict(result.total_score, language)

    mangal_note = None
    if result.mangal_dosha_mismatch:
        mangal_note = (
            "एक साथी मंगलिक है और दूसरा नहीं — पारंपरिक रूप से इसकी अलग से जांच सुझाई जाती है।"
            if language == "hi"
            else "One partner is Manglik and the other isn't — traditionally worth checking separately from the Ashtakoot score."
        )

    sign_names = SIGN_NAMES_HI if language == "hi" else SIGN_NAMES_EN
    nakshatra_names = NAKSHATRA_NAMES_HI if language == "hi" else NAKSHATRA_NAMES_EN

    return GunaMilanResponse(
        language=language,
        your_moon_sign=sign_names[moon_self.sign_index],
        your_nakshatra=nakshatra_names[nakshatra_self],
        partner_moon_sign=sign_names[partner_moon_sign],
        partner_nakshatra=nakshatra_names[nakshatra_partner],
        total_score=result.total_score,
        max_total=result.max_total,
        kootas=_build_koota_list(result, language),
        mangal_dosha_mismatch=result.mangal_dosha_mismatch,
        mangal_dosha_note=mangal_note,
        verdict=band,
        verdict_message=verdict_message,
    )
