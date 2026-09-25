"""Deterministic (no GPT) "does THIS specific business type suit me"
assessment — see the plan's Phase 7. Deliberately distinct from
prediction_service.get_decision("business_start"), which already answers a
different question: "is now a good time to start *a* business" (7th-house
lord + current dasha score + dusthana affliction + transit corroboration).
This module answers "does *clothing*/*steel*/*consulting* specifically fit
this chart" — a real gap: nothing before this combined the industry-bucket
table with the wealth/partnership/gains houses or the yoga list.

Multi-signal by design, per explicit instruction: never a single
`strongest_planet == business_planet` binary rule. Every signal combined
here is something the chat pipeline already computes for every request
(context["strongest_planet_code"]/["weakest_planet_code"],
context["house_verdict_bucket"], context["yogas"],
context["business_start_decision"]) — this module only combines them, it
never invents a new astrological rule."""

# Classical planet -> business/industry correspondences — the reverse
# direction of native_response._INDUSTRY_SUGGESTIONS_EN (which goes
# planet -> suggested industries; this goes business-type text -> matching
# planet bucket). Kept as simple keyword buckets, not a scoring model.
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Su": ("government", "leadership", "politics", "administration"),
    "Mo": ("food", "restaurant", "hospitality", "dairy", "beverage"),
    "Ma": ("steel", "metal", "engineering", "electrical", "machinery", "construction"),
    "Me": ("trade", "media", "writing", "consulting", "it", "tech", "software", "communication"),
    "Ju": ("education", "finance", "law", "banking", "teaching"),
    "Ve": ("clothing", "fashion", "beauty", "design", "art", "jewelry", "cosmetics"),
    "Sa": ("real estate", "manufacturing", "mining", "agriculture"),
    "Ra": ("import", "export", "technology startup", "foreign trade", "aviation"),
    "Ke": ("research", "healing", "alternative medicine", "spiritual"),
}

# The 3 houses genuinely relevant to "will a business go well" beyond
# straight career timing: wealth (2nd), partnerships/trade (7th, the SAME
# house business_start_decision's own timing verdict already keys off),
# gains/income realization (11th). Not the full 12 — a business-suitability
# read has no honest signal from, say, the 4th (home) or 9th (fortune) house.
_RELEVANT_HOUSES = (2, 7, 11)


def _match_bucket(business_type_text: str) -> str | None:
    text = (business_type_text or "").lower()
    for planet_code, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return planet_code
    return None


def _wealth_house_signal(house_verdict_bucket: dict[int, str]) -> str:
    buckets = [house_verdict_bucket.get(h) for h in _RELEVANT_HOUSES if house_verdict_bucket.get(h)]
    if not buckets:
        return "mixed"
    favorable = buckets.count("favorable")
    unfavorable = buckets.count("unfavorable")
    if favorable > unfavorable:
        return "supportive"
    if unfavorable > favorable:
        return "challenging"
    return "mixed"


def _supportive_yoga_present(yogas: list[dict]) -> bool:
    # There is no dedicated "wealth yoga" (Dhana Yoga) detector anywhere in
    # this codebase (checked: app.services.chart_explanation_service.
    # detect_yogas only ever produces "gajakesari", "mahapurusha_<planet>",
    # and "raj_yoga") — inventing one here to fabricate a wealth signal would
    # be exactly the "invented astrology rule" this module must never do.
    # The two REAL, already-detected yogas most classically read as a
    # general success/prosperity boost are Raj Yoga (status/success) and
    # Gajakesari (steady good fortune) — matched by the chart engine's own
    # stable `key`, not by re-parsing description text.
    supportive_keys = {"raj_yoga", "gajakesari"}
    return any((y.get("key") or "") in supportive_keys for y in (yogas or []))


def _combine_overall(planet_alignment: str | None, wealth_house_signal: str, supportive_yoga_present: bool) -> str:
    """A documented, simple combine of the per-signal verdicts — not a new
    scoring model. supportive/challenging require at least two signals
    agreeing; a single strong signal alone only ever reaches "mixed"."""
    supportive_votes = int(planet_alignment == "supportive") + int(wealth_house_signal == "supportive") + int(supportive_yoga_present)
    challenging_votes = int(planet_alignment == "challenging") + int(wealth_house_signal == "challenging")
    if supportive_votes >= 2 and supportive_votes > challenging_votes:
        return "supportive"
    if challenging_votes >= 2 and challenging_votes > supportive_votes:
        return "challenging"
    if supportive_votes and challenging_votes:
        return "mixed"
    if supportive_votes or challenging_votes:
        return "mixed"
    return "mixed"


def assess_business_category_suitability(
    business_type_text: str,
    strongest_planet_code: str | None,
    house_verdict_bucket: dict[int, str],
    yogas: list[dict],
    business_start_decision: dict | None,
    weakest_planet_code: str | None = None,
) -> dict:
    """Returns a structured, multi-signal verdict — never a single boolean.

    {
      "category_recognized": bool,
      "matched_bucket": str | None,       # planet code, e.g. "Ve"
      "planet_alignment": "supportive" | "challenging" | "neutral" | None,
      "wealth_house_signal": "supportive" | "challenging" | "mixed",
      "supportive_yoga_present": bool,    # Raj Yoga or Gajakesari, the only
                                           # already-detected general success/
                                           # prosperity yogas in this codebase
      "timing_signal": str | None,        # business_start_decision's own verdict, passed through
      "overall": "supportive" | "challenging" | "mixed" | "insufficient_data",
      "reasoning": list[str],
    }

    category_recognized=False (no keyword match for business_type_text at
    all) -> overall="insufficient_data" always, never silently substituted
    with a generic career-timing read."""
    matched_bucket = _match_bucket(business_type_text)
    if matched_bucket is None:
        return {
            "category_recognized": False,
            "matched_bucket": None,
            "planet_alignment": None,
            "wealth_house_signal": "mixed",
            "supportive_yoga_present": False,
            "timing_signal": (business_start_decision or {}).get("verdict"),
            "overall": "insufficient_data",
            "reasoning": ["business type not recognized against any known industry bucket"],
        }

    if strongest_planet_code and matched_bucket == strongest_planet_code:
        planet_alignment = "supportive"
    elif weakest_planet_code and matched_bucket == weakest_planet_code:
        planet_alignment = "challenging"
    elif strongest_planet_code:
        planet_alignment = "neutral"
    else:
        planet_alignment = None

    wealth_house_signal = _wealth_house_signal(house_verdict_bucket or {})
    supportive_yoga_present = _supportive_yoga_present(yogas)
    overall = _combine_overall(planet_alignment, wealth_house_signal, supportive_yoga_present)

    reasoning = [f"business type maps to the {matched_bucket} bucket"]
    if planet_alignment:
        reasoning.append(f"strongest-planet alignment is {planet_alignment}")
    reasoning.append(f"2nd/7th/11th house signal is {wealth_house_signal}")
    if supportive_yoga_present:
        reasoning.append("a supportive yoga (Raj Yoga or Gajakesari) is present in the chart")
    timing_signal = (business_start_decision or {}).get("verdict")
    if timing_signal:
        reasoning.append(f"business-start timing verdict is {timing_signal}")

    return {
        "category_recognized": True,
        "matched_bucket": matched_bucket,
        "planet_alignment": planet_alignment,
        "wealth_house_signal": wealth_house_signal,
        "supportive_yoga_present": supportive_yoga_present,
        "timing_signal": timing_signal,
        "overall": overall,
        "reasoning": reasoning,
    }
