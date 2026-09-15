"""Generic dasha-timeline window scanner: score every Antardasha window in a
person's life against a caller-supplied rule set, and return the
highest-scoring windows from a given moment onward.

This is the reusable engine behind marriage-timing prediction
(app.astro.marriage_timing) — deliberately generic so a future event-timing
predictor (e.g. career milestones, financial growth windows) is a new rule
set passed to `scan_dasha_windows`, not new scanning architecture.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.astro.constants import DAYS_PER_YEAR, PlanetKey, planet_relation
from app.astro.dasha import Mahadasha


@dataclass(frozen=True)
class WindowRule:
    """Scores an Antardasha window whenever the given level's ruling lord
    equals `target`."""

    applies_to: str  # "antardasha_lord" | "mahadasha_lord"
    target: PlanetKey
    weight: float
    reason_key: str


@dataclass(frozen=True)
class ScoredWindow:
    start: datetime
    end: datetime
    mahadasha_lord: PlanetKey
    antardasha_lord: PlanetKey
    score: float
    reason_keys: list[str]


# How well the Antardasha lord classically "cooperates" with the Mahadasha
# it runs inside — real astrologers read a period's likely smoothness partly
# from this relationship (Dasha-Antardasha sambandha), not from the
# Antardasha lord's significations alone. The same planet ruling both levels
# ("same") is the strongest, most unmixed expression of that planet's
# results; a natural enemy pair classically produces a more mixed or
# obstructed period even when the classical rule set above scores it highly.
# See app.astro.constants.planet_relation for the underlying friendship
# table (also used by app.astro.guna_milan's Graha Maitri koota).
_DASHA_RELATIONSHIP_MULTIPLIER: dict[str, float] = {
    "same": 1.2, "friend": 1.1, "neutral": 1.0, "enemy": 0.85,
}


def _dasha_relationship(mahadasha_lord: PlanetKey, antardasha_lord: PlanetKey) -> str:
    if mahadasha_lord == antardasha_lord:
        return "same"
    return planet_relation(mahadasha_lord, antardasha_lord)


def scan_dasha_windows(
    mahadashas: list[Mahadasha],
    rules: list[WindowRule],
    from_dt: datetime,
    horizon_years: float,
    weigh_dasha_relationship: bool = False,
) -> list[ScoredWindow]:
    """Walks every Antardasha window overlapping [from_dt, from_dt +
    horizon_years), scores each against `rules`, and returns only windows
    with a non-zero score — highest score first, ties broken by earliest
    start. A window that starts before `from_dt` or ends after `horizon_end`
    is clipped to those bounds on the corresponding side — every returned
    window's [start, end) is fully contained in [from_dt, horizon_end),
    which matters for a past-direction search: an Antardasha that's still
    ongoing (started in the past, hasn't ended "today") must not be reported
    with an end date out in the future.

    `weigh_dasha_relationship=True` scales each window's classical rule score
    by the Mahadasha/Antardasha lords' natural relationship (see
    _DASHA_RELATIONSHIP_MULTIPLIER) and adds a "dasha_relationship_{same,
    friend,enemy}" reason key whenever that relationship isn't the neutral
    default — silent for "neutral" so most windows don't carry a note that
    says nothing. Defaults to False so existing callers/tests that expect
    scores to equal a plain sum of rule weights are unaffected."""
    horizon_end = from_dt + timedelta(days=horizon_years * DAYS_PER_YEAR)

    scored: list[ScoredWindow] = []
    for maha in mahadashas:
        for antar in maha.antardashas:
            if antar.end <= from_dt or antar.start >= horizon_end:
                continue
            score = 0.0
            reasons: list[str] = []
            for rule in rules:
                lord = antar.lord if rule.applies_to == "antardasha_lord" else maha.lord
                if lord == rule.target:
                    score += rule.weight
                    reasons.append(rule.reason_key)
            if score > 0:
                if weigh_dasha_relationship:
                    relationship = _dasha_relationship(maha.lord, antar.lord)
                    score *= _DASHA_RELATIONSHIP_MULTIPLIER[relationship]
                    if relationship != "neutral":
                        reasons.append(f"dasha_relationship_{relationship}")
                scored.append(
                    ScoredWindow(
                        start=max(antar.start, from_dt),
                        end=min(antar.end, horizon_end),
                        mahadasha_lord=maha.lord,
                        antardasha_lord=antar.lord,
                        score=score,
                        reason_keys=reasons,
                    )
                )
    scored.sort(key=lambda w: (-w.score, w.start))
    return scored
