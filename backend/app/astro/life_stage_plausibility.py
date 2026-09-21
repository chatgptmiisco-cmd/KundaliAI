"""Real-world age-plausibility weighting for the Prediction Engine's life-
event timing (app.astro.marriage_timing, app.astro.life_event_timing).

This is deliberately NOT classical astrology — it's the "does this even
make sense for a human life" sanity check a real astrologer applies
automatically, which the classical dasha/transit math has no concept of at
all. Vimshottari dasha math treats every stretch of a person's ~120-year
computed timeline as equally valid for "marriage" or "having children" — in
practice this let the Prediction Engine's own "same lord running both dasha
levels" bonus (app.astro.event_window_scanner.weigh_dasha_relationship,
which fires at maximum strength for EVERY chart's very first Antardasha,
since the birth Mahadasha's own first Antardasha is structurally always the
same planet) rank a person's own first few months of infancy as their #1
classical "career" or "children" window — a real, computed classical
signal, but not a serious answer to "when will I have kids."

Each event type gets a documented, deliberately SOFT (not hard-cutoff) age
band: implausible ages are heavily discounted rather than excluded
outright, in case a real classical signal genuinely falls outside the
typical range and there's nothing better in the search horizon — this
mirrors how every other Prediction Engine factor (natal strength, dasha
relationship, transit corroboration/obstruction) TILTS the classical score
rather than zeroing a window out completely.
"""
from typing import Literal

EventCategory = Literal[
    "marriage", "career", "wealth", "children", "foreign_travel",
    "career_promotion", "business_partnership", "business_expansion",
    "property",
]

# (hard_floor, soft_floor, soft_ceiling, hard_ceiling), in years of age at
# the window's START. Below hard_floor or above hard_ceiling: heavily
# discounted (_MIN_MULTIPLIER), AND — since is_hard_implausible_age below —
# treated as not a sensible LITERAL reading of the event at all (see that
# function). Between hard_floor/soft_floor or soft_ceiling/hard_ceiling:
# ramps linearly. Between soft_floor/soft_ceiling: full weight — the
# "typical" range for this event in most lives, not a hard classical rule,
# just ordinary real-world sense.
_AGE_BANDS: dict[EventCategory, tuple[float, float, float, float]] = {
    "marriage": (15.0, 19.0, 45.0, 60.0),
    "career": (13.0, 17.0, 65.0, 75.0),
    # hard_floor=16 (not 13, like career) — independently-earned personal
    # wealth is a materially later real-world milestone than "a career" (a
    # first job, an apprenticeship) even where both start young. Found by
    # comparing this engine's own output against independent chart reads: a
    # 13-15 year old's chart could otherwise still return a literal
    # personal-wealth prediction, just heavily discounted rather than
    # reinterpreted.
    "wealth": (16.0, 19.0, 70.0, 80.0),
    "children": (15.0, 19.0, 48.0, 55.0),
    # Foreign travel/relocation genuinely happens at almost any age (family
    # relocation as a child, work travel as an adult, retirement travel) —
    # a much wider, gentler band than the other four.
    "foreign_travel": (0.0, 3.0, 75.0, 90.0),
    # Phase 2 sub-intents reuse their closest parent domain's band rather
    # than inventing new numbers — a promotion's age relevance is career's;
    # business-partnership timing (adult, formal-commitment-level relevance
    # via the shared 7th house) is closest to marriage's; business
    # expansion (financial-gain timing) is closest to wealth's.
    "career_promotion": (13.0, 17.0, 65.0, 75.0),
    "business_partnership": (15.0, 19.0, 45.0, 60.0),
    "business_expansion": (16.0, 19.0, 70.0, 80.0),
    # Phase 5: buying a house is a financial/asset milestone, closest to
    # wealth's own age relevance — reuses wealth's exact band rather than
    # inventing new numbers, same convention as the three reuses above.
    "property": (16.0, 19.0, 70.0, 80.0),
}

_MIN_MULTIPLIER = 0.15


def age_plausibility_multiplier(event_type: EventCategory, age_years: float) -> float:
    hard_floor, soft_floor, soft_ceiling, hard_ceiling = _AGE_BANDS[event_type]
    if age_years <= hard_floor or age_years >= hard_ceiling:
        return _MIN_MULTIPLIER
    if age_years < soft_floor:
        t = (age_years - hard_floor) / (soft_floor - hard_floor)
        return _MIN_MULTIPLIER + t * (1.0 - _MIN_MULTIPLIER)
    if age_years > soft_ceiling:
        t = (age_years - soft_ceiling) / (hard_ceiling - soft_ceiling)
        return 1.0 - t * (1.0 - _MIN_MULTIPLIER)
    return 1.0


def is_hard_implausible_age(event_type: EventCategory, age_years: float) -> bool:
    """True at or beyond the HARD floor/ceiling — not merely outside the
    softer "typical" band `is_implausible_age` flags. Past this point a
    LITERAL reading of the event (an actual first marriage, an actual
    childbirth, independently-earned personal wealth) stops being a
    sensible real-world interpretation no matter how strong the classical
    dasha signal is — found by comparing this engine's own output against
    independent chart reads: a technically well-supported window (the
    correct house lord's own Antardasha) at age 14 for "wealth" or age 63
    for "children" was still being returned as the literal top answer,
    since the continuous `age_plausibility_multiplier` above only ever
    TILTS the score rather than ruling a reading out. Callers should prefer
    a plausible-age alternative window when one exists in the search
    horizon (see prediction_service._select_candidate_pool), and when one
    doesn't, present the window as a REINTERPRETED signal rather than a
    literal one (see prediction_templates.py's reinterpretation sentence)."""
    hard_floor, _, _, hard_ceiling = _AGE_BANDS[event_type]
    return age_years <= hard_floor or age_years >= hard_ceiling


def is_implausible_age(event_type: EventCategory, age_years: float) -> Literal["early", "late"] | None:
    """For surfacing an honest note in the reason text (see
    prediction_templates.py) rather than only ever affecting ranking
    silently — same convention as every other Prediction Engine factor.
    Returns None inside the soft band (nothing worth remarking on)."""
    hard_floor, soft_floor, soft_ceiling, hard_ceiling = _AGE_BANDS[event_type]
    if age_years < soft_floor:
        return "early"
    if age_years > soft_ceiling:
        return "late"
    return None
