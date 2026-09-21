from datetime import date
from typing import Literal

from pydantic import BaseModel


class LifeStateIn(BaseModel):
    """Deterministic life facts the Prediction Engine uses to decide WHICH
    question a chart is answering (see app.services.prediction_service) —
    not astrology inputs, just current-state ones. Every field is optional:
    a user who hasn't filled this in gets the engine's existing
    from-birth-facts-alone behavior, unchanged."""

    # "dating"/"engaged" added for chat-driven capture (see
    # chat_understanding.LifeStateUpdate) — a user who says "I'm engaged"
    # is meaningfully past "single" for marriage-timing reinterpretation
    # purposes but not yet "married"; prediction_service's `already_married`
    # check only ever matches the literal "married" value, so this widening
    # doesn't change any existing redirect behavior for single/married/
    # divorced/widowed users.
    marital_status: Literal["single", "dating", "engaged", "married", "divorced", "widowed"] | None = None
    marriage_date: date | None = None
    children_count: int = 0
    pregnancy_status: Literal["none", "expecting"] = "none"
    expected_delivery: date | None = None
    career_state: Literal["employed", "unemployed", "student"] | None = None
    business_state: Literal["none", "running", "considering"] | None = None
    # Phase 8 — property_purchase engine's life-state gate.
    housing_status: Literal["renting", "owns_property", "living_with_parents", "other"] | None = None
    planning_property_purchase: bool = False
    has_home_loan: bool = False


class LifeStateOut(LifeStateIn):
    version: int
