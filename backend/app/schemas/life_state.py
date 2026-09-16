from datetime import date
from typing import Literal

from pydantic import BaseModel


class LifeStateIn(BaseModel):
    """Deterministic life facts the Prediction Engine uses to decide WHICH
    question a chart is answering (see app.services.prediction_service) —
    not astrology inputs, just current-state ones. Every field is optional:
    a user who hasn't filled this in gets the engine's existing
    from-birth-facts-alone behavior, unchanged."""

    marital_status: Literal["single", "married", "divorced", "widowed"] | None = None
    marriage_date: date | None = None
    children_count: int = 0
    pregnancy_status: Literal["none", "expecting"] = "none"
    expected_delivery: date | None = None
    career_state: Literal["employed", "unemployed", "student"] | None = None
    business_state: Literal["none", "running", "considering"] | None = None


class LifeStateOut(LifeStateIn):
    version: int
