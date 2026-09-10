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

from app.astro.constants import DAYS_PER_YEAR, PlanetKey
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


def scan_dasha_windows(
    mahadashas: list[Mahadasha],
    rules: list[WindowRule],
    from_dt: datetime,
    horizon_years: float,
) -> list[ScoredWindow]:
    """Walks every Antardasha window overlapping [from_dt, from_dt +
    horizon_years), scores each against `rules`, and returns only windows
    with a non-zero score — highest score first, ties broken by earliest
    start. A window that has already started but not yet ended is clipped to
    start at `from_dt` (it's still "ahead", just already underway)."""
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
                scored.append(
                    ScoredWindow(
                        start=max(antar.start, from_dt),
                        end=antar.end,
                        mahadasha_lord=maha.lord,
                        antardasha_lord=antar.lord,
                        score=score,
                        reason_keys=reasons,
                    )
                )
    scored.sort(key=lambda w: (-w.score, w.start))
    return scored
